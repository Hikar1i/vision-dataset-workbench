import re
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import func, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..models import ProjectLabel, User
from .projects import ProjectForbidden, ProjectService


class LabelNotFound(ValueError):
    pass


class LabelConflict(ValueError):
    pass


class InvalidLabel(ValueError):
    pass


@dataclass(frozen=True)
class LabelChanges:
    name: str | None = None
    description_zh: str | None = None
    color: str | None = None
    enabled: bool | None = None


_NAME_PATTERN = re.compile(r"^[a-z0-9](?:[a-z0-9 _-]{0,62}[a-z0-9])?$")
_COLOR_PATTERN = re.compile(r"^#[0-9a-f]{6}$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def normalize_label_name(value: str) -> str:
    normalized = " ".join(value.strip().lower().split())
    if not _NAME_PATTERN.fullmatch(normalized):
        raise InvalidLabel(
            "label name must use 1-64 lowercase letters, numbers, spaces, hyphens, or underscores"
        )
    return normalized


def _label_color(value: str) -> str:
    normalized = value.strip().lower()
    if not _COLOR_PATTERN.fullmatch(normalized):
        raise InvalidLabel("label color must be a six-digit hex color")
    return normalized


def _label_description_zh(value: str) -> str:
    description = value.strip()
    if len(description) > 64:
        raise InvalidLabel("label Chinese description must not exceed 64 characters")
    return description


class LabelService:
    def __init__(self, engine: Engine, projects: ProjectService):
        self.projects = projects
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def list_labels(self, actor: User, project_id: str) -> list[ProjectLabel]:
        self.projects.get_project(actor, project_id)
        with self._session_factory() as database:
            return list(
                database.scalars(
                    select(ProjectLabel)
                    .where(ProjectLabel.project_id == project_id)
                    .order_by(ProjectLabel.sort_order, ProjectLabel.id)
                )
            )

    def create_label(
        self,
        actor: User,
        project_id: str,
        name: str,
        description_zh: str,
        color: str,
    ) -> ProjectLabel:
        self._require_write(actor, project_id)
        clean_name = normalize_label_name(name)
        clean_description_zh = _label_description_zh(description_zh)
        clean_color = _label_color(color)
        now = _utc_now()
        with self._session_factory() as database:
            last_order = database.scalar(
                select(func.max(ProjectLabel.sort_order)).where(
                    ProjectLabel.project_id == project_id
                )
            )
            label = ProjectLabel(
                id=str(uuid4()),
                project_id=project_id,
                name=clean_name,
                name_normalized=clean_name,
                description_zh=clean_description_zh,
                color=clean_color,
                sort_order=0 if last_order is None else last_order + 1,
                enabled=True,
                version=1,
                created_at=now,
                updated_at=now,
            )
            try:
                database.add(label)
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise LabelConflict("label name already exists in this project") from exc
            return label

    def update_label(
        self,
        actor: User,
        project_id: str,
        label_id: str,
        changes: LabelChanges,
        *,
        version: int,
    ) -> ProjectLabel:
        self._require_write(actor, project_id)
        values: dict[str, object] = {}
        if changes.name is not None:
            clean_name = normalize_label_name(changes.name)
            values.update(name=clean_name, name_normalized=clean_name)
        if changes.description_zh is not None:
            values["description_zh"] = _label_description_zh(changes.description_zh)
        if changes.color is not None:
            values["color"] = _label_color(changes.color)
        if changes.enabled is not None:
            values["enabled"] = changes.enabled
        if not values:
            raise InvalidLabel("at least one label field must be changed")
        values.update(updated_at=_utc_now(), version=ProjectLabel.version + 1)

        with self._session_factory() as database:
            current = database.scalar(
                select(ProjectLabel).where(
                    ProjectLabel.id == label_id,
                    ProjectLabel.project_id == project_id,
                )
            )
            if current is None:
                raise LabelNotFound("label not found")
            try:
                result = database.execute(
                    update(ProjectLabel)
                    .where(ProjectLabel.id == label_id, ProjectLabel.version == version)
                    .values(**values)
                    .execution_options(synchronize_session=False)
                )
                if result.rowcount != 1:
                    database.rollback()
                    raise LabelConflict("label was modified by another user")
                database.commit()
                database.expire_all()
            except IntegrityError as exc:
                database.rollback()
                raise LabelConflict("label name already exists in this project") from exc
            updated = database.get(ProjectLabel, label_id)
            assert updated is not None
            return updated

    def reorder_labels(
        self, actor: User, project_id: str, label_ids: list[str]
    ) -> list[ProjectLabel]:
        self._require_write(actor, project_id)
        with self._session_factory() as database:
            labels = list(
                database.scalars(
                    select(ProjectLabel).where(ProjectLabel.project_id == project_id)
                )
            )
            current_ids = {label.id for label in labels}
            if len(label_ids) != len(current_ids) or set(label_ids) != current_ids:
                raise InvalidLabel("label order must contain every project label exactly once")
            by_id = {label.id: label for label in labels}
            now = _utc_now()
            for sort_order, label_id in enumerate(label_ids):
                label = by_id[label_id]
                label.sort_order = sort_order
                label.version += 1
                label.updated_at = now
            database.commit()
            return [by_id[label_id] for label_id in label_ids]

    def delete_label(self, actor: User, project_id: str, label_id: str) -> None:
        self._require_write(actor, project_id)
        with self._session_factory() as database:
            label = database.scalar(
                select(ProjectLabel).where(
                    ProjectLabel.id == label_id,
                    ProjectLabel.project_id == project_id,
                )
            )
            if label is None:
                raise LabelNotFound("label not found")
            database.delete(label)
            remaining = list(
                database.scalars(
                    select(ProjectLabel)
                    .where(
                        ProjectLabel.project_id == project_id,
                        ProjectLabel.id != label_id,
                    )
                    .order_by(ProjectLabel.sort_order, ProjectLabel.id)
                )
            )
            now = _utc_now()
            for sort_order, item in enumerate(remaining):
                if item.sort_order != sort_order:
                    item.sort_order = sort_order
                    item.version += 1
                    item.updated_at = now
            database.commit()

    def _require_write(self, actor: User, project_id: str) -> None:
        if self.projects.get_project(actor, project_id).role == "viewer":
            raise ProjectForbidden("project edit permission required")
