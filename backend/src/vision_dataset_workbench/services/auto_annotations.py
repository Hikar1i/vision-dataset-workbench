import hashlib
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..capabilities import SystemCapabilities
from ..config import RuntimeSettings
from ..inference import Detection, InferenceRunner, InferenceUnavailable
from ..models import ProjectLabel, User, Video
from .annotations import AnnotationInput
from .labels import LabelConflict, LabelService, normalize_label_name
from .models import ModelService
from .projects import ProjectForbidden, ProjectService
from .sampling import SamplingService


class AutoAnnotationUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class DraftAnnotation:
    annotation: AnnotationInput
    label_name: str


@dataclass(frozen=True)
class AutoAnnotationResult:
    items: list[DraftAnnotation]
    created_labels: list[ProjectLabel]


_COLORS = (
    "#e85d4a",
    "#2f80ed",
    "#f2a900",
    "#8e5ad7",
    "#00a6a6",
    "#d94f91",
    "#6b9e2e",
    "#e07a1f",
)


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
        runner: InferenceRunner | None = None,
    ):
        self.workspace = workspace.resolve()
        self.projects = projects
        self.models = models
        self.labels = labels
        self.capabilities = capabilities
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
    ) -> AutoAnnotationResult:
        if self.projects.get_project(actor, project_id).role == "viewer":
            raise ProjectForbidden("project edit permission required")
        model, model_path = self.models.ready_model(model_id)
        capability = (
            self.capabilities.features.yolo_auto_annotation
            if model.kind == "yolo"
            else self.capabilities.features.grounding_dino_auto_annotation
        )
        if not capability.available:
            raise AutoAnnotationUnavailable(capability.reason or "auto annotation unavailable")
        frame, image_path = self.sampling.ready_frame_file(
            actor, project_id, video_id, frame_id
        )
        prompts = list(dict.fromkeys(normalize_label_name(item) for item in categories))
        if model.kind == "grounding_dino" and not prompts:
            prompts = [
                item.name
                for item in self.labels.list_labels(actor, project_id)
                if item.enabled
            ]
        try:
            detections = self.runner.predict(
                model, model_path, image_path, prompts, confidence, iou
            )
        except InferenceUnavailable as exc:
            raise AutoAnnotationUnavailable(str(exc)) from exc
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
                        confidence=max(0.0, min(1.0, detection.confidence)),
                    ),
                    clean_name,
                )
            )
        return AutoAnnotationResult(items, created)

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
            digest = hashlib.sha256(name.encode()).digest()[0]
            try:
                label = self.labels.create_label(
                    actor, project_id, name, "", _COLORS[digest % len(_COLORS)]
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
