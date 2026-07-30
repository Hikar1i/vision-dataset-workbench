import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..config import RuntimeSettings
from ..models import Frame, FrameAnnotation, SamplingPlan, Task, User, Video
from ..sampling import SamplingInput, calculate_sampling
from .projects import ProjectForbidden, ProjectService


class SamplingNotFound(ValueError):
    pass


class SamplingConflict(ValueError):
    def __init__(self, message: str, code: str = "sampling_conflict"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class SamplingNotice:
    input: str
    reason: str
    code: str = "invalid_request"


@dataclass(frozen=True)
class AcceptedPlan:
    video_id: str
    plan: SamplingPlan


@dataclass(frozen=True)
class PlanBatch:
    accepted: list[AcceptedPlan]
    rejected: list[SamplingNotice]


@dataclass(frozen=True)
class AcceptedExtraction:
    video_id: str
    task: Task


@dataclass(frozen=True)
class ExtractionBatch:
    accepted: list[AcceptedExtraction]
    rejected: list[SamplingNotice]


@dataclass(frozen=True)
class SamplingSummary:
    id: str
    state: str
    mode: str
    parameters: dict[str, int]
    output_format: str
    output_quality: int
    computed_interval: int | None
    expected_frames: int
    extracted_frames: int
    enabled_frames: int
    version: int
    applied_version: int
    generation: int
    frame_revision: int
    updated_at: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def sampling_summary(plan: SamplingPlan) -> SamplingSummary:
    state = (
        "sampled"
        if plan.applied_version == plan.version and plan.extracted_frames > 0
        else "configured"
    )
    return SamplingSummary(
        id=plan.id,
        state=state,
        mode=plan.mode,
        parameters=json.loads(plan.parameters),
        output_format=plan.output_format,
        output_quality=plan.output_quality,
        computed_interval=plan.computed_interval,
        expected_frames=plan.expected_frames,
        extracted_frames=plan.extracted_frames,
        enabled_frames=plan.enabled_frames,
        version=plan.version,
        applied_version=plan.applied_version,
        generation=plan.generation,
        frame_revision=plan.frame_revision,
        updated_at=plan.updated_at,
    )


class SamplingService:
    def __init__(
        self,
        engine: Engine,
        settings: RuntimeSettings,
        workspace: Path,
    ):
        self.engine = engine
        self.settings = settings
        self.workspace = workspace.resolve()
        self._projects = ProjectService(engine, settings, workspace)
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def _project_role(self, actor: User, project_id: str) -> str:
        return self._projects.get_project(actor, project_id).role

    def _require_editor(self, actor: User, project_id: str) -> None:
        if self._project_role(actor, project_id) == "viewer":
            raise ProjectForbidden("project edit permission required")

    @staticmethod
    def _video(database, project_id: str, video_id: str) -> Video:
        video = database.get(Video, video_id)
        if video is None or video.project_id != project_id:
            raise SamplingNotFound("video not found")
        return video

    @staticmethod
    def _active_task(database, video_id: str) -> bool:
        return (
            database.scalar(
                select(Task.id).where(
                    Task.video_id == video_id,
                    Task.status.in_(("queued", "running")),
                )
            )
            is not None
        )

    @staticmethod
    def _active_extraction(database, video_id: str) -> bool:
        return (
            database.scalar(
                select(Task.id).where(
                    Task.video_id == video_id,
                    Task.type == "extract_frames",
                    Task.status.in_(("queued", "running")),
                )
            )
            is not None
        )

    @staticmethod
    def _has_annotations(database, video_id: str) -> bool:
        return (
            database.scalar(
                select(FrameAnnotation.id)
                .join(Frame, Frame.id == FrameAnnotation.frame_id)
                .where(Frame.video_id == video_id)
                .limit(1)
            )
            is not None
        )

    @staticmethod
    def _validate_output(output_format: str, output_quality: int) -> None:
        valid = (output_format == "jpg" and 1 <= output_quality <= 31) or (
            output_format == "png" and 0 <= output_quality <= 9
        )
        if not valid:
            raise ValueError("frame output format or quality is invalid")

    def configure(
        self,
        actor: User,
        project_id: str,
        video_ids: list[str],
        sampling_input: SamplingInput,
        output_format: str,
        output_quality: int,
        overwrite_level: str = "none",
    ) -> PlanBatch:
        self._require_editor(actor, project_id)
        self._validate_output(output_format, output_quality)
        accepted: list[AcceptedPlan] = []
        rejected: list[SamplingNotice] = []
        overwrite_rank = {"none": 0, "configured": 1, "sampled": 2}
        if overwrite_level not in overwrite_rank:
            raise ValueError("sampling overwrite level is invalid")
        seen: set[str] = set()
        for video_id in video_ids[:999]:
            if video_id in seen:
                rejected.append(
                    SamplingNotice(video_id, "duplicate selection", "duplicate_selection")
                )
                continue
            seen.add(video_id)
            try:
                with self._session_factory() as database:
                    video = self._video(database, project_id, video_id)
                    if video.status != "ready":
                        raise SamplingConflict("video is not ready", "video_not_ready")
                    if self._active_task(database, video_id):
                        raise SamplingConflict(
                            "video already has an active task", "active_task"
                        )
                    estimate = calculate_sampling(
                        video.total_frames,
                        video.fps,
                        video.duration,
                        sampling_input,
                    )
                    plan = database.scalar(
                        select(SamplingPlan).where(SamplingPlan.video_id == video_id)
                    )
                    if plan is not None:
                        required_level = (
                            "sampled" if plan.extracted_frames > 0 else "configured"
                        )
                        if overwrite_rank[overwrite_level] < overwrite_rank[required_level]:
                            code = (
                                "sampled_plan_locked"
                                if required_level == "sampled"
                                else "sampling_plan_exists"
                            )
                            raise SamplingConflict(
                                f"{required_level} sampling overwrite confirmation required",
                                code,
                            )
                    now = _utc_now()
                    if plan is None:
                        plan = SamplingPlan(
                            id=str(uuid4()),
                            video_id=video_id,
                            mode=estimate.mode,
                            parameters=json.dumps(estimate.parameters),
                            output_format=output_format,
                            output_quality=output_quality,
                            computed_interval=estimate.computed_interval,
                            expected_frames=estimate.expected_frames,
                            created_at=now,
                            updated_at=now,
                        )
                        database.add(plan)
                    else:
                        plan.mode = estimate.mode
                        plan.parameters = json.dumps(estimate.parameters)
                        plan.output_format = output_format
                        plan.output_quality = output_quality
                        plan.computed_interval = estimate.computed_interval
                        plan.expected_frames = estimate.expected_frames
                        plan.version += 1
                        plan.updated_at = now
                    database.commit()
                    database.expunge(plan)
                    accepted.append(AcceptedPlan(video_id, plan))
            except (SamplingNotFound, SamplingConflict, ValueError) as exc:
                rejected.append(
                    SamplingNotice(
                        video_id,
                        str(exc),
                        getattr(exc, "code", "invalid_request"),
                    )
                )
        return PlanBatch(accepted, rejected)

    def create_extractions(
        self,
        actor: User,
        project_id: str,
        video_ids: list[str],
        overwrite_level: str = "none",
    ) -> ExtractionBatch:
        self._require_editor(actor, project_id)
        accepted: list[AcceptedExtraction] = []
        rejected: list[SamplingNotice] = []
        overwrite_rank = {"none": 0, "light": 1, "destructive": 2}
        if overwrite_level not in overwrite_rank:
            raise ValueError("extraction overwrite level is invalid")
        seen: set[str] = set()
        for video_id in video_ids[:999]:
            if video_id in seen:
                rejected.append(
                    SamplingNotice(video_id, "duplicate selection", "duplicate_selection")
                )
                continue
            seen.add(video_id)
            try:
                with self._session_factory() as database:
                    video = self._video(database, project_id, video_id)
                    if video.status != "ready":
                        raise SamplingConflict("video is not ready", "video_not_ready")
                    if self._active_task(database, video_id):
                        raise SamplingConflict(
                            "video already has an active task", "active_task"
                        )
                    plan = database.scalar(
                        select(SamplingPlan).where(SamplingPlan.video_id == video_id)
                    )
                    if plan is None:
                        raise SamplingConflict(
                            "sampling plan is not configured", "sampling_plan_missing"
                        )
                    if plan.extracted_frames > 0:
                        required_level = (
                            "destructive"
                            if plan.frame_revision > 1
                            or self._has_annotations(database, video_id)
                            else "light"
                        )
                        if overwrite_rank[overwrite_level] < overwrite_rank[required_level]:
                            raise SamplingConflict(
                                f"{required_level} overwrite confirmation required",
                                f"{required_level}_overwrite_required",
                            )
                    now = _utc_now()
                    task = Task(
                        id=str(uuid4()),
                        project_id=project_id,
                        submitted_by_id=actor.id,
                        video_id=video_id,
                        type="extract_frames",
                        payload=json.dumps({"sampling_plan_version": plan.version}),
                        created_at=now,
                        updated_at=now,
                    )
                    database.add(task)
                    database.commit()
                    database.expunge(task)
                    accepted.append(AcceptedExtraction(video_id, task))
            except (SamplingNotFound, SamplingConflict, IntegrityError) as exc:
                reason = (
                    "video already has an active task"
                    if isinstance(exc, IntegrityError)
                    else str(exc)
                )
                rejected.append(
                    SamplingNotice(
                        video_id,
                        reason,
                        "active_task"
                        if isinstance(exc, IntegrityError)
                        else getattr(exc, "code", "invalid_request"),
                    )
                )
        return ExtractionBatch(accepted, rejected)

    def videos_with_annotations(
        self, actor: User, project_id: str, video_ids: list[str]
    ) -> set[str]:
        self._project_role(actor, project_id)
        if not video_ids:
            return set()
        with self._session_factory() as database:
            return set(
                database.scalars(
                    select(Frame.video_id)
                    .join(FrameAnnotation, FrameAnnotation.frame_id == Frame.id)
                    .join(Video, Video.id == Frame.video_id)
                    .where(
                        Video.project_id == project_id,
                        Frame.video_id.in_(video_ids),
                    )
                    .distinct()
                )
            )

    def get_plan(
        self, actor: User, project_id: str, video_id: str
    ) -> SamplingPlan | None:
        self._project_role(actor, project_id)
        with self._session_factory() as database:
            self._video(database, project_id, video_id)
            plan = database.scalar(
                select(SamplingPlan).where(SamplingPlan.video_id == video_id)
            )
            if plan is not None:
                database.expunge(plan)
            return plan

    def summaries(
        self, actor: User, project_id: str, video_ids: list[str]
    ) -> dict[str, SamplingSummary]:
        self._project_role(actor, project_id)
        if not video_ids:
            return {}
        with self._session_factory() as database:
            plans = database.scalars(
                select(SamplingPlan).where(SamplingPlan.video_id.in_(video_ids))
            ).all()
            return {plan.video_id: sampling_summary(plan) for plan in plans}

    def list_frames(
        self,
        actor: User,
        project_id: str,
        video_id: str,
        *,
        page: int,
        page_size: int,
        enabled: bool | None,
    ) -> tuple[list[Frame], int, SamplingPlan]:
        self._project_role(actor, project_id)
        with self._session_factory() as database:
            self._video(database, project_id, video_id)
            plan = database.scalar(
                select(SamplingPlan).where(SamplingPlan.video_id == video_id)
            )
            if plan is None:
                raise SamplingNotFound("sampling plan not found")
            where = [Frame.video_id == video_id]
            if enabled is not None:
                where.append(Frame.enabled.is_(enabled))
            total = database.scalar(
                select(func.count()).select_from(Frame).where(*where)
            ) or 0
            frames = database.scalars(
                select(Frame)
                .where(*where)
                .order_by(Frame.sequence)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            database.expunge(plan)
            for frame in frames:
                database.expunge(frame)
            return list(frames), total, plan

    def ready_frame_file(
        self,
        actor: User,
        project_id: str,
        video_id: str,
        frame_id: str,
    ) -> tuple[Frame, Path]:
        self._project_role(actor, project_id)
        with self._session_factory() as database:
            video = self._video(database, project_id, video_id)
            frame = database.get(Frame, frame_id)
            if frame is None or frame.video_id != video_id:
                raise SamplingNotFound("frame not found")
            try:
                path = (self.workspace / frame.file_path).resolve(strict=True)
            except OSError as exc:
                raise SamplingNotFound("frame file not found") from exc
            root = (
                self.workspace
                / "projects"
                / project_id
                / "frames"
                / video.short_code
            ).resolve()
            if not path.is_file() or not path.is_relative_to(root):
                raise SamplingNotFound("frame file not found")
            database.expunge(frame)
        return frame, path

    def frame_annotation_previews(
        self,
        actor: User,
        project_id: str,
        video_id: str,
        frame_ids: list[str],
    ) -> dict[str, list[FrameAnnotation]]:
        self._project_role(actor, project_id)
        if not frame_ids:
            return {}
        with self._session_factory() as database:
            self._video(database, project_id, video_id)
            items = database.scalars(
                select(FrameAnnotation)
                .join(Frame, Frame.id == FrameAnnotation.frame_id)
                .where(
                    Frame.video_id == video_id,
                    FrameAnnotation.frame_id.in_(frame_ids),
                )
                .order_by(
                    FrameAnnotation.frame_id,
                    FrameAnnotation.sort_order,
                    FrameAnnotation.id,
                )
            ).all()
            result: dict[str, list[FrameAnnotation]] = {}
            for item in items:
                result.setdefault(item.frame_id, []).append(item)
                database.expunge(item)
            return result

    def annotated_frame_ids(
        self,
        actor: User,
        project_id: str,
        video_id: str,
    ) -> list[str]:
        self._project_role(actor, project_id)
        with self._session_factory() as database:
            self._video(database, project_id, video_id)
            return list(
                database.scalars(
                    select(Frame.id)
                    .join(FrameAnnotation, FrameAnnotation.frame_id == Frame.id)
                    .where(Frame.video_id == video_id)
                    .group_by(Frame.id, Frame.sequence)
                    .order_by(Frame.sequence)
                )
            )

    def set_frames_enabled(
        self,
        actor: User,
        project_id: str,
        video_id: str,
        changes: dict[str, bool],
        *,
        revision: int,
    ) -> SamplingPlan:
        self._require_editor(actor, project_id)
        with self._session_factory() as database:
            self._video(database, project_id, video_id)
            plan = database.scalar(
                select(SamplingPlan).where(SamplingPlan.video_id == video_id)
            )
            if plan is None or plan.extracted_frames == 0:
                raise SamplingConflict("video has no sampled frames")
            if self._active_extraction(database, video_id):
                raise SamplingConflict(
                    "frame changes are locked while extraction is active",
                    "active_extraction",
                )
            if plan.frame_revision != revision:
                raise SamplingConflict("frame revision conflict")
            frame_ids = set(changes)
            matched = database.scalar(
                select(func.count())
                .select_from(Frame)
                .where(Frame.video_id == video_id, Frame.id.in_(frame_ids))
            ) or 0
            if matched != len(frame_ids):
                raise SamplingNotFound("frame not found")
            for enabled in (True, False):
                matching_ids = [
                    frame_id
                    for frame_id, value in changes.items()
                    if value is enabled
                ]
                if matching_ids:
                    database.execute(
                        update(Frame)
                        .where(
                            Frame.video_id == video_id,
                            Frame.id.in_(matching_ids),
                        )
                        .values(enabled=enabled)
                    )
            plan.enabled_frames = database.scalar(
                select(func.count())
                .select_from(Frame)
                .where(Frame.video_id == video_id, Frame.enabled.is_(True))
            ) or 0
            plan.frame_revision += 1
            plan.updated_at = _utc_now()
            database.commit()
            database.expunge(plan)
            return plan
