import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..config import RuntimeSettings
from ..media import RemotePreview, normalize_remote_url, preview_remote
from ..models import Task, User, Video
from ..storage.browser import VIDEO_EXTENSIONS
from ..storage.paths import HomePathResolver, UnsafePathError
from .projects import ProjectForbidden, ProjectService


class MediaNotFound(ValueError):
    pass


class MediaConflict(ValueError):
    pass


@dataclass(frozen=True)
class LocalPreview:
    path: str
    name: str
    size: int


@dataclass(frozen=True)
class AcceptedImport:
    video: Video
    task: Task


@dataclass(frozen=True)
class ImportNotice:
    input: str
    reason: str


@dataclass(frozen=True)
class ImportBatch:
    accepted: list[AcceptedImport]
    skipped: list[ImportNotice]
    rejected: list[ImportNotice]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class MediaService:
    def __init__(
        self,
        engine: Engine,
        settings: RuntimeSettings,
        workspace: Path,
        *,
        previewer: Callable[[str, RuntimeSettings], list[RemotePreview]] = preview_remote,
    ):
        self.engine = engine
        self.settings = settings
        self.workspace = workspace.resolve()
        self._previewer = previewer
        self._projects = ProjectService(engine, settings, workspace)
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def _project_role(self, actor: User, project_id: str) -> str:
        return self._projects.get_project(actor, project_id).role

    def _require_editor(self, actor: User, project_id: str) -> None:
        if self._project_role(actor, project_id) == "viewer":
            raise ProjectForbidden("project edit permission required")

    def _source_path(self, relative: str) -> Path:
        resolver = HomePathResolver(self.settings.home)
        path = resolver.resolve_existing(relative)
        if path == self.workspace or path.is_relative_to(self.workspace):
            raise UnsafePathError("managed workspace is not an import source")
        return path

    def preview_local(
        self, actor: User, project_id: str, relative: str
    ) -> list[LocalPreview]:
        self._require_editor(actor, project_id)
        source = self._source_path(relative)
        candidates = [source] if source.is_file() else list(source.iterdir())
        files = sorted(
            (
                item
                for item in candidates
                if item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS
            ),
            key=lambda item: item.name.casefold(),
        )
        resolver = HomePathResolver(self.settings.home)
        return [
            LocalPreview(
                path=item.relative_to(resolver.home).as_posix(),
                name=item.name,
                size=item.stat().st_size,
            )
            for item in files
        ]

    def preview_remote(
        self, actor: User, project_id: str, url: str
    ) -> list[RemotePreview]:
        self._require_editor(actor, project_id)
        return self._previewer(normalize_remote_url(url), self.settings)

    def import_local(
        self, actor: User, project_id: str, paths: Sequence[str]
    ) -> ImportBatch:
        self._require_editor(actor, project_id)
        accepted: list[AcceptedImport] = []
        skipped: list[ImportNotice] = []
        rejected: list[ImportNotice] = []
        seen: set[str] = set()
        for relative in paths[:999]:
            if relative in seen:
                skipped.append(ImportNotice(relative, "duplicate selection"))
                continue
            seen.add(relative)
            try:
                source = self._source_path(relative)
                if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
                    raise ValueError("source is not a supported video file")
                accepted.append(
                    self._create_import(
                        actor,
                        project_id,
                        source_type="local",
                        title=source.stem,
                        source_name=source.name,
                        payload={"source_path": relative},
                        task_type="copy_video",
                    )
                )
            except (OSError, UnsafePathError, ValueError) as exc:
                rejected.append(ImportNotice(relative, str(exc)))
        return ImportBatch(accepted, skipped, rejected)

    def import_remote(
        self,
        actor: User,
        project_id: str,
        items: Sequence[tuple[str, str]],
    ) -> ImportBatch:
        self._require_editor(actor, project_id)
        accepted: list[AcceptedImport] = []
        skipped: list[ImportNotice] = []
        rejected: list[ImportNotice] = []
        seen: set[str] = set()
        for title, raw_url in items[:999]:
            try:
                url = normalize_remote_url(raw_url)
                if url in seen:
                    skipped.append(ImportNotice(url, "duplicate selection"))
                    continue
                seen.add(url)
                accepted.append(
                    self._create_import(
                        actor,
                        project_id,
                        source_type="remote",
                        title=title.strip()[:512] or "Remote video",
                        source_url=url,
                        payload={"url": url},
                        task_type="download_video",
                    )
                )
            except ValueError as exc:
                rejected.append(ImportNotice(raw_url, str(exc)))
        return ImportBatch(accepted, skipped, rejected)

    def _create_import(
        self,
        actor: User,
        project_id: str,
        *,
        source_type: str,
        title: str,
        payload: dict[str, str],
        task_type: str,
        source_name: str | None = None,
        source_url: str | None = None,
    ) -> AcceptedImport:
        now = _utc_now()
        video = Video(
            id=str(uuid4()),
            project_id=project_id,
            source_type=source_type,
            title=title,
            source_name=source_name,
            source_url=source_url,
            status="pending",
            created_at=now,
            updated_at=now,
        )
        task = Task(
            id=str(uuid4()),
            project_id=project_id,
            submitted_by_id=actor.id,
            video_id=video.id,
            type=task_type,
            status="queued",
            payload=json.dumps(payload, ensure_ascii=False),
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as database:
            database.add(video)
            database.flush()
            database.add(task)
            database.commit()
        return AcceptedImport(video, task)

    def list_videos(
        self, actor: User, project_id: str, *, page: int, page_size: int
    ) -> tuple[list[Video], int]:
        self._project_role(actor, project_id)
        with self._session_factory() as database:
            where = Video.project_id == project_id
            total = database.scalar(select(func.count()).select_from(Video).where(where)) or 0
            items = database.scalars(
                select(Video)
                .where(where)
                .order_by(Video.created_at.desc(), Video.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return list(items), total

    def list_tasks(
        self, actor: User, project_id: str, *, page: int, page_size: int
    ) -> tuple[list[Task], int]:
        self._project_role(actor, project_id)
        with self._session_factory() as database:
            where = Task.project_id == project_id
            total = database.scalar(select(func.count()).select_from(Task).where(where)) or 0
            items = database.scalars(
                select(Task)
                .where(where)
                .order_by(Task.created_at.desc(), Task.id)
                .offset((page - 1) * page_size)
                .limit(page_size)
            ).all()
            return list(items), total

    def cancel_task(self, actor: User, project_id: str, task_id: str) -> Task:
        self._require_editor(actor, project_id)
        now = _utc_now()
        with self._session_factory() as database:
            task = database.get(Task, task_id)
            if task is None or task.project_id != project_id:
                raise MediaNotFound("task not found")
            if task.status == "queued":
                task.status = "canceled"
                task.finished_at = now
            elif task.status == "running":
                task.cancel_requested = True
            else:
                raise MediaConflict("task cannot be canceled")
            task.updated_at = now
            database.commit()
            return task

    def retry_task(self, actor: User, project_id: str, task_id: str) -> Task:
        self._require_editor(actor, project_id)
        now = _utc_now()
        with self._session_factory() as database:
            previous = database.get(Task, task_id)
            if previous is None or previous.project_id != project_id:
                raise MediaNotFound("task not found")
            if previous.status not in {"failed", "canceled"} or previous.video_id is None:
                raise MediaConflict("only failed or canceled tasks can be retried")
            video = database.get(Video, previous.video_id)
            if video is None:
                raise MediaConflict("task video no longer exists")
            video.status = "pending"
            video.updated_at = now
            task = Task(
                id=str(uuid4()),
                project_id=project_id,
                submitted_by_id=actor.id,
                video_id=video.id,
                type=previous.type,
                status="queued",
                payload=previous.payload,
                retry_of_id=previous.id,
                created_at=now,
                updated_at=now,
            )
            database.add(task)
            database.commit()
            return task
