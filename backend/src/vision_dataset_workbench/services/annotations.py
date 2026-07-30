from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..models import Frame, FrameAnnotation, ProjectLabel, Task, User, Video
from .projects import ProjectForbidden, ProjectService


class AnnotationNotFound(ValueError):
    pass


class AnnotationConflict(ValueError):
    pass


class InvalidAnnotation(ValueError):
    pass


@dataclass(frozen=True)
class AnnotationInput:
    id: str
    label_id: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int
    source: str = "manual"
    confidence: float | None = None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AnnotationService:
    def __init__(self, engine: Engine, projects: ProjectService):
        self.projects = projects
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def list_frame(
        self,
        actor: User,
        project_id: str,
        video_id: str,
        frame_id: str,
    ) -> tuple[Frame, list[FrameAnnotation]]:
        self.projects.get_project(actor, project_id)
        with self._session_factory() as database:
            frame, _video = self._context(database, project_id, video_id, frame_id)
            items = self._ordered_items(database, frame_id)
            database.expunge(frame)
            for item in items:
                database.expunge(item)
            return frame, items

    def replace_frame(
        self,
        actor: User,
        project_id: str,
        video_id: str,
        frame_id: str,
        revision: int,
        items: list[AnnotationInput],
    ) -> tuple[Frame, list[FrameAnnotation]]:
        if self.projects.get_project(actor, project_id).role == "viewer":
            raise ProjectForbidden("project edit permission required")
        with self._session_factory() as database:
            frame, video = self._context(database, project_id, video_id, frame_id)
            active_task = database.scalar(
                select(Task.id).where(
                    Task.video_id == video_id,
                    Task.type.in_(("auto_annotate", "extract_frames")),
                    Task.status.in_(("queued", "running")),
                )
            )
            if active_task is not None:
                raise AnnotationConflict(
                    "annotation changes are locked while a video task is active"
                )
            self._validate_items(database, project_id, video, items)
            changed = database.execute(
                update(Frame)
                .where(Frame.id == frame_id, Frame.annotation_revision == revision)
                .values(annotation_revision=revision + 1)
                .execution_options(synchronize_session=False)
            )
            if changed.rowcount != 1:
                database.rollback()
                raise AnnotationConflict("annotation revision conflict")
            database.execute(
                delete(FrameAnnotation).where(FrameAnnotation.frame_id == frame_id)
            )
            now = _utc_now()
            database.add_all(
                [
                    FrameAnnotation(
                        id=item.id,
                        frame_id=frame_id,
                        label_id=item.label_id,
                        x_min=item.x_min,
                        y_min=item.y_min,
                        x_max=item.x_max,
                        y_max=item.y_max,
                        source=item.source,
                        confidence=item.confidence,
                        sort_order=sort_order,
                        created_at=now,
                    )
                    for sort_order, item in enumerate(items)
                ]
            )
            database.commit()
            database.expire_all()
            saved_frame = database.get(Frame, frame_id)
            assert saved_frame is not None
            saved_items = self._ordered_items(database, frame_id)
            database.expunge(saved_frame)
            for item in saved_items:
                database.expunge(item)
            return saved_frame, saved_items

    @staticmethod
    def _context(database, project_id: str, video_id: str, frame_id: str):
        video = database.get(Video, video_id)
        if video is None or video.project_id != project_id:
            raise AnnotationNotFound("video not found")
        frame = database.get(Frame, frame_id)
        if frame is None or frame.video_id != video_id:
            raise AnnotationNotFound("frame not found")
        return frame, video

    @staticmethod
    def _ordered_items(database, frame_id: str) -> list[FrameAnnotation]:
        return list(
            database.scalars(
                select(FrameAnnotation)
                .where(FrameAnnotation.frame_id == frame_id)
                .order_by(FrameAnnotation.sort_order, FrameAnnotation.id)
            )
        )

    @staticmethod
    def _validate_items(
        database,
        project_id: str,
        video: Video,
        items: list[AnnotationInput],
    ) -> None:
        ids = [item.id for item in items]
        if len(ids) != len(set(ids)):
            raise InvalidAnnotation("annotation ids must be unique")
        label_ids = {item.label_id for item in items}
        if label_ids:
            found = set(
                database.scalars(
                    select(ProjectLabel.id).where(
                        ProjectLabel.project_id == project_id,
                        ProjectLabel.id.in_(label_ids),
                    )
                )
            )
            if found != label_ids:
                raise InvalidAnnotation("annotation label does not belong to project")
        for item in items:
            if not (
                0 <= item.x_min < item.x_max <= video.width
                and 0 <= item.y_min < item.y_max <= video.height
            ):
                raise InvalidAnnotation("annotation bounds exceed image dimensions")
            if item.source not in {"manual", "model"}:
                raise InvalidAnnotation("annotation source is invalid")
            if item.confidence is not None and not 0 <= item.confidence <= 1:
                raise InvalidAnnotation("annotation confidence must be between 0 and 1")
