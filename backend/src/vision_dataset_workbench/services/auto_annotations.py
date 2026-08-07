import json
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..capabilities import SystemCapabilities
from ..config import RuntimeSettings
from ..inference import Detection, InferenceRunner, InferenceUnavailable
from ..models import Frame, ProjectLabel, Task, User, Video
from .annotations import AnnotationInput
from .labels import (
    LabelConflict,
    LabelService,
    automatic_label_color,
    normalize_label_name,
)
from .models import ModelService
from .projects import ProjectForbidden, ProjectService
from .sampling import SamplingService
from .xanylabeling_settings import XAnyLabelingSettingsService
from .dataset_exports import video_has_active_export
from ..xanylabeling import XAnyLabelingUnavailable


class AutoAnnotationUnavailable(ValueError):
    pass


class AutoAnnotationConflict(ValueError):
    pass


@dataclass(frozen=True)
class DraftAnnotation:
    annotation: AnnotationInput
    label_name: str


@dataclass(frozen=True)
class AutoAnnotationResult:
    items: list[DraftAnnotation]
    created_labels: list[ProjectLabel]


@dataclass(frozen=True)
class AutoAnnotationModel:
    source: str
    model_id: str
    remote_task_id: str | None = None


@dataclass(frozen=True)
class AutoAnnotationBatchResult:
    task: Task
    accepted_video_ids: list[str]
    rejected: list[dict[str, str]]


class AutoAnnotationService:
    def __init__(
        self,
        engine: Engine,
        settings: RuntimeSettings,
        workspace: Path,
        projects: ProjectService,
        models: ModelService,
        labels: LabelService,
        capabilities: SystemCapabilities,
        remote_settings: XAnyLabelingSettingsService,
        runner: InferenceRunner | None = None,
    ):
        self.workspace = workspace.resolve()
        self.projects = projects
        self.models = models
        self.labels = labels
        self.capabilities = capabilities
        self.remote_settings = remote_settings
        self.runner = runner or InferenceRunner()
        self.sampling = SamplingService(engine, settings, workspace)
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def run_frame(
        self,
        actor: User,
        project_id: str,
        video_id: str,
        frame_id: str,
        model_id: str,
        categories: list[str],
        confidence: float,
        iou: float,
        source: str = "local",
        remote_task_id: str | None = None,
    ) -> AutoAnnotationResult:
        if self.projects.get_project(actor, project_id).role == "viewer":
            raise ProjectForbidden("project edit permission required")
        frame, image_path = self.sampling.ready_frame_file(
            actor, project_id, video_id, frame_id
        )
        prompts = list(dict.fromkeys(normalize_label_name(item) for item in categories))
        detections = self._predict(
            actor,
            AutoAnnotationModel(source, model_id, remote_task_id),
            image_path,
            prompts,
            confidence,
            iou,
        )
        with self._session_factory() as database:
            video = database.get(Video, video_id)
            if video is None or video.project_id != project_id or frame.video_id != video_id:
                raise AutoAnnotationUnavailable("video or frame no longer exists")
            width, height = video.width, video.height
        valid = []
        for detection in detections:
            clean_name = normalize_label_name(detection.label)
            bounds = self._bounds(detection, width, height)
            if bounds is None:
                continue
            valid.append((detection, clean_name, bounds))
        label_map, created = self._ensure_labels(
            actor, project_id, [item[0] for item in valid]
        )
        items = []
        for detection, clean_name, bounds in valid:
            items.append(
                DraftAnnotation(
                    AnnotationInput(
                        id=str(uuid4()),
                        label_id=label_map[clean_name].id,
                        **bounds,
                        source="model",
                        confidence=(
                            max(0.0, min(1.0, detection.confidence))
                            if detection.confidence is not None
                            else None
                        ),
                    ),
                    clean_name,
                )
            )
        return AutoAnnotationResult(items, created)

    def create_batch(
        self,
        actor: User,
        project_id: str,
        video_id: str,
        model_id: str,
        categories: list[str],
        confidence: float,
        iou: float,
        overwrite: bool,
        source: str = "local",
        remote_task_id: str | None = None,
    ) -> Task:
        if self.projects.get_project(actor, project_id).role == "viewer":
            raise ProjectForbidden("project edit permission required")
        selection = AutoAnnotationModel(source, model_id, remote_task_id)
        self._validate_model(actor, selection)
        prompts = list(dict.fromkeys(normalize_label_name(item) for item in categories))
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        with self._session_factory() as database:
            video = database.get(Video, video_id)
            if video is None or video.project_id != project_id:
                raise AutoAnnotationUnavailable("video not found")
            if video_has_active_export(database, project_id, video_id):
                raise AutoAnnotationConflict(
                    "video is frozen by an active dataset export"
                )
            if not video.enabled:
                raise AutoAnnotationConflict("video is disabled")
            enabled_frames = database.scalar(
                select(func.count())
                .select_from(Frame)
                .where(Frame.video_id == video_id, Frame.enabled.is_(True))
            ) or 0
            if enabled_frames == 0:
                raise AutoAnnotationConflict("video has no enabled sampled frames")
            active = database.scalar(
                select(Task.id).where(
                    Task.video_id == video_id,
                    Task.status.in_(("queued", "running")),
                )
            )
            if active is not None:
                raise AutoAnnotationConflict("video already has an active task")
            task = Task(
                id=str(uuid4()),
                project_id=project_id,
                submitted_by_id=actor.id,
                video_id=video_id,
                type="auto_annotate",
                payload=json.dumps(
                    {
                        "source": source,
                        "model_id": model_id,
                        "remote_task_id": remote_task_id,
                        "categories": prompts,
                        "confidence": confidence,
                        "iou": iou,
                        "overwrite": overwrite,
                    },
                    ensure_ascii=False,
                ),
                created_at=now,
                updated_at=now,
            )
            try:
                database.add(task)
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise AutoAnnotationConflict("video already has an active task") from exc
            database.expunge(task)
            return task

    def create_project_batch(
        self,
        actor: User,
        project_id: str,
        video_ids: list[str],
        model_id: str,
        categories: list[str],
        confidence: float,
        iou: float,
        overwrite: bool,
        scope: str = "all",
        source: str = "local",
        remote_task_id: str | None = None,
    ) -> AutoAnnotationBatchResult:
        if self.projects.get_project(actor, project_id).role == "viewer":
            raise ProjectForbidden("project edit permission required")
        if scope not in {"unannotated", "all"}:
            raise AutoAnnotationConflict("invalid batch annotation scope")
        if len(set(video_ids)) != len(video_ids):
            raise AutoAnnotationConflict("video ids must be unique")
        selection = AutoAnnotationModel(source, model_id, remote_task_id)
        self._validate_model(actor, selection)
        prompts = list(dict.fromkeys(normalize_label_name(item) for item in categories))
        rejected: list[dict[str, str]] = []
        accepted: list[str] = []
        with self._session_factory() as database:
            active_batch_video_ids: set[str] = set()
            for active_task in database.scalars(
                select(Task).where(
                    Task.project_id == project_id,
                    Task.type == "auto_annotate",
                    Task.video_id.is_(None),
                    Task.status.in_(("queued", "running")),
                )
            ):
                active_batch_video_ids.update(json.loads(active_task.payload).get("video_ids", []))
            for video_id in video_ids:
                video = database.get(Video, video_id)
                if video is None or video.project_id != project_id:
                    rejected.append({"video_id": video_id, "reason": "video not found"})
                    continue
                if scope == "unannotated" and self.sampling._has_annotations(database, video_id):
                    rejected.append({"video_id": video_id, "reason": "video already has annotations"})
                    continue
                if video_has_active_export(database, project_id, video_id):
                    rejected.append({"video_id": video_id, "reason": "video is frozen by an active dataset export"})
                    continue
                if not video.enabled:
                    rejected.append({"video_id": video_id, "reason": "video is disabled"})
                    continue
                enabled_frames = database.scalar(
                    select(func.count())
                    .select_from(Frame)
                    .where(Frame.video_id == video_id, Frame.enabled.is_(True))
                ) or 0
                if enabled_frames == 0:
                    rejected.append({"video_id": video_id, "reason": "video has no enabled sampled frames"})
                    continue
                active = database.scalar(
                    select(Task.id).where(
                        Task.video_id == video_id,
                        Task.status.in_(("queued", "running")),
                    )
                )
                if active is not None:
                    rejected.append({"video_id": video_id, "reason": "video already has an active task"})
                    continue
                if video_id in active_batch_video_ids:
                    rejected.append({"video_id": video_id, "reason": "video already has an active task"})
                    continue
                accepted.append(video_id)
            if not accepted:
                raise AutoAnnotationConflict("no videos are eligible for batch annotation")
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            task = Task(
                id=str(uuid4()),
                project_id=project_id,
                submitted_by_id=actor.id,
                video_id=None,
                type="auto_annotate",
                payload=json.dumps(
                    {
                        "video_ids": accepted,
                        "source": source,
                        "model_id": model_id,
                        "remote_task_id": remote_task_id,
                        "categories": prompts,
                        "confidence": confidence,
                        "iou": iou,
                        "overwrite": overwrite,
                        "batch": True,
                    },
                    ensure_ascii=False,
                ),
                created_at=now,
                updated_at=now,
            )
            database.add(task)
            database.commit()
            database.expunge(task)
            return AutoAnnotationBatchResult(task, accepted, rejected)

    def _predict(
        self,
        actor: User,
        selection: AutoAnnotationModel,
        image_path: Path,
        categories: list[str],
        confidence: float,
        iou: float,
    ) -> list[Detection]:
        resolved = self._validate_model(actor, selection)
        try:
            if selection.source == "local":
                model, model_path = resolved
                return self.runner.predict(
                    model, model_path, image_path, categories, confidence, iou
                )
            client, option = resolved
            return client.predict(option, image_path, categories, confidence, iou)
        except (InferenceUnavailable, XAnyLabelingUnavailable) as exc:
            raise AutoAnnotationUnavailable(str(exc)) from exc

    def _validate_model(
        self, actor: User, selection: AutoAnnotationModel
    ) -> tuple[object, object]:
        if selection.source == "local":
            model, model_path = self.models.ready_model(selection.model_id)
            capability = self.capabilities.features.yolo_auto_annotation
            if not capability.available:
                raise AutoAnnotationUnavailable(
                    capability.reason or "auto annotation unavailable"
                )
            return model, model_path
        if selection.source != "xanylabeling":
            raise AutoAnnotationUnavailable("unsupported auto annotation source")
        try:
            client = self.remote_settings.client_for(actor.id)
            option = next(
                (
                    item
                    for item in client.list_models()
                    if item.model_id == selection.model_id
                    and item.task_id == selection.remote_task_id
                ),
                None,
            )
        except ValueError as exc:
            raise AutoAnnotationUnavailable(str(exc)) from exc
        if option is None:
            raise AutoAnnotationUnavailable("remote model is no longer available")
        return client, option

    def _ensure_labels(
        self,
        actor: User,
        project_id: str,
        detections: list[Detection],
    ) -> tuple[dict[str, ProjectLabel], list[ProjectLabel]]:
        names = list(dict.fromkeys(normalize_label_name(item.label) for item in detections))
        existing = {
            item.name_normalized: item
            for item in self.labels.list_labels(actor, project_id)
        }
        created = []
        for name in names:
            if name in existing:
                continue
            try:
                label = self.labels.create_label(
                    actor, project_id, name, "", automatic_label_color(name)
                )
            except LabelConflict:
                label = next(
                    item
                    for item in self.labels.list_labels(actor, project_id)
                    if item.name_normalized == name
                )
            existing[name] = label
            created.append(label)
        return existing, created

    @staticmethod
    def _bounds(detection: Detection, width: int, height: int):
        x_min = max(0, min(width, round(detection.x_min)))
        y_min = max(0, min(height, round(detection.y_min)))
        x_max = max(0, min(width, round(detection.x_max)))
        y_max = max(0, min(height, round(detection.y_max)))
        if x_max - x_min < 2 or y_max - y_min < 2:
            return None
        return {"x_min": x_min, "y_min": y_min, "x_max": x_max, "y_max": y_max}
