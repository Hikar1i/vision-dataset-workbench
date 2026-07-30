import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..dataset_export import safe_export_name
from ..models import DatasetExport, Frame, ProjectLabel, SamplingPlan, Task, User, Video
from .projects import ProjectForbidden, ProjectService


class DatasetExportNotFound(ValueError):
    pass


class DatasetExportConflict(ValueError):
    pass


class InvalidDatasetExport(ValueError):
    pass


@dataclass(frozen=True)
class ExportLabelInput:
    source_label_id: str
    name: str
    mapping: int
    enabled: bool


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class DatasetExportService:
    def __init__(
        self,
        engine: Engine,
        workspace: Path,
        projects: ProjectService,
        *,
        now=_utc_now,
    ):
        self.workspace = workspace.resolve()
        self.projects = projects
        self._now = now
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def create(
        self,
        actor: User,
        project_id: str,
        name: str,
        train_ratio: float,
        labels: list[ExportLabelInput],
    ) -> DatasetExport:
        if self.projects.get_project(actor, project_id).role == "viewer":
            raise ProjectForbidden("project edit permission required")
        clean_name = name.strip()
        if not 1 <= len(clean_name) <= 128 or not safe_export_name(clean_name):
            raise InvalidDatasetExport("dataset name must contain 1-128 usable characters")
        if not 0 <= train_ratio <= 1:
            raise InvalidDatasetExport("train ratio must be between 0 and 1")

        now = self._now()
        export_id = str(uuid4())
        task_id = str(uuid4())
        with self._session_factory() as database:
            database.connection().exec_driver_sql("BEGIN IMMEDIATE")
            stored_labels = list(
                database.scalars(
                    select(ProjectLabel)
                    .where(ProjectLabel.project_id == project_id)
                    .order_by(ProjectLabel.sort_order, ProjectLabel.id)
                )
            )
            label_snapshot = self._validate_labels(labels, stored_labels)
            videos = list(
                database.execute(
                    select(Video, SamplingPlan)
                    .join(SamplingPlan, SamplingPlan.video_id == Video.id)
                    .where(
                        Video.project_id == project_id,
                        Video.enabled.is_(True),
                        Video.status == "ready",
                        SamplingPlan.extracted_frames > 0,
                    )
                    .order_by(Video.id)
                )
            )
            video_ids = [video.id for video, _plan in videos]
            counts = dict(
                database.execute(
                    select(Frame.video_id, func.count(Frame.id))
                    .join(SamplingPlan, SamplingPlan.video_id == Frame.video_id)
                    .where(
                        Frame.video_id.in_(video_ids),
                        Frame.enabled.is_(True),
                        Frame.generation == SamplingPlan.generation,
                    )
                    .group_by(Frame.video_id)
                ).all()
            ) if video_ids else {}
            source_videos = [
                {
                    "video_id": video.id,
                    "video_version": video.version,
                    "sampling_generation": plan.generation,
                    "frame_revision": plan.frame_revision,
                    "enabled_frames": counts.get(video.id, 0),
                }
                for video, plan in videos
                if counts.get(video.id, 0) > 0
            ]
            if not source_videos:
                raise DatasetExportConflict("project has no enabled sampled frames to export")

            record = DatasetExport(
                id=export_id,
                project_id=project_id,
                task_id=task_id,
                created_by_id=actor.id,
                name=clean_name,
                status="queued",
                train_ratio=train_ratio,
                label_snapshot=json.dumps(label_snapshot, ensure_ascii=False),
                source_snapshot=json.dumps({"videos": source_videos}),
                created_at=now,
            )
            task = Task(
                id=task_id,
                project_id=project_id,
                submitted_by_id=actor.id,
                video_id=None,
                type="export_dataset",
                status="queued",
                payload=json.dumps({"export_id": export_id}),
                created_at=now,
                updated_at=now,
            )
            try:
                database.add(task)
                database.flush()
                database.add(record)
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise DatasetExportConflict(
                    "project already has an active dataset export"
                ) from exc
            return record

    def list_exports(
        self,
        actor: User,
        project_id: str,
        *,
        page: int,
        page_size: int,
    ) -> tuple[list[DatasetExport], int]:
        self.projects.get_project(actor, project_id)
        with self._session_factory() as database:
            filters = (
                DatasetExport.project_id == project_id,
                DatasetExport.deleted_at.is_(None),
            )
            total = database.scalar(
                select(func.count()).select_from(DatasetExport).where(*filters)
            ) or 0
            items = list(
                database.scalars(
                    select(DatasetExport)
                    .where(*filters)
                    .order_by(DatasetExport.created_at.desc(), DatasetExport.id)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return items, total

    def get(self, actor: User, project_id: str, export_id: str) -> DatasetExport:
        self.projects.get_project(actor, project_id)
        with self._session_factory() as database:
            record = database.scalar(
                select(DatasetExport).where(
                    DatasetExport.id == export_id,
                    DatasetExport.project_id == project_id,
                    DatasetExport.deleted_at.is_(None),
                )
            )
            if record is None:
                raise DatasetExportNotFound("dataset export not found")
            return record

    @staticmethod
    def _validate_labels(
        requested: list[ExportLabelInput], stored: list[ProjectLabel]
    ) -> list[dict[str, object]]:
        if len(requested) != len(stored) or {item.source_label_id for item in requested} != {
            item.id for item in stored
        }:
            raise InvalidDatasetExport(
                "label snapshot must contain every project label exactly once"
            )
        by_id = {item.id: item for item in stored}
        snapshot: list[dict[str, object]] = []
        for expected_mapping, item in enumerate(requested):
            label = by_id[item.source_label_id]
            if item.mapping != expected_mapping:
                raise InvalidDatasetExport("label mappings must be continuous from zero")
            if item.name != label.name:
                raise InvalidDatasetExport("label snapshot does not match project labels")
            snapshot.append(
                {
                    "source_label_id": item.source_label_id,
                    "name": item.name,
                    "mapping": item.mapping,
                    "enabled": item.enabled,
                }
            )
        if not any(bool(item["enabled"]) for item in snapshot):
            raise InvalidDatasetExport("at least one label must be enabled")
        return snapshot
