import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import case, delete, or_, select, update
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..config import RuntimeSettings
from ..models import (
    OFFICIAL_YOLO11_SYSTEM_KEY,
    InferenceModel,
    ModelArtifact,
    ModelEvaluation,
    ModelInferenceRun,
    ModelProject,
    ModelProjectMembership,
    ModelProjectTag,
    ModelProjectTagLink,
    Task,
    User,
)
from ..storage.browser import MODEL_EXTENSIONS
from ..storage.paths import HomePathResolver, UnsafePathError
from .auth import normalize_username
from .authorization import (
    AccessContext,
    Permission,
    access_for_role,
    administrator_access,
    system_resource_access,
)
from .projects import ProjectService


class ModelNotFound(ValueError):
    pass


class ModelForbidden(ValueError):
    pass


class ModelConflict(ValueError):
    pass


class InvalidModel(ValueError):
    pass


class InvalidModelMember(ValueError):
    pass


@dataclass(frozen=True)
class RegisteredModel:
    model: InferenceModel
    task: Task


@dataclass(frozen=True)
class ModelMemberView:
    user: User
    role: str
    created_at: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def touch_model_project(
    database: Session, project_id: str, *, at: datetime | None = None
) -> None:
    database.execute(
        update(ModelProject)
        .where(ModelProject.id == project_id, ModelProject.deleted_at.is_(None))
        .values(updated_at=at or _utc_now())
        .execution_options(synchronize_session=False)
    )


def touch_training_model_project(
    database: Session, training_task_id: str, *, at: datetime | None = None
) -> None:
    database.execute(
        update(ModelProject)
        .where(
            ModelProject.training_task_id == training_task_id,
            ModelProject.deleted_at.is_(None),
        )
        .values(updated_at=at or _utc_now())
        .execution_options(synchronize_session=False)
    )


def _clean_text(value: str, maximum: int, field: str, *, required: bool = False) -> str:
    clean = " ".join(value.strip().split())
    if (required and not clean) or len(clean) > maximum:
        qualifier = f"1-{maximum}" if required else f"0-{maximum}"
        raise InvalidModel(f"{field} must contain {qualifier} characters")
    return clean


def _normalized_name(value: str) -> str:
    return _clean_text(value, 128, "model project name", required=True).lower()


def _code(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.rsplit(".", 1)[0].lower()).strip("-")
    return (clean or "model")[:48]


class ModelService:
    def __init__(
        self,
        engine: Engine,
        settings: RuntimeSettings,
        workspace: Path,
        projects: ProjectService,
    ):
        self.settings = settings
        self.workspace = workspace.resolve()
        self.projects = projects
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    @staticmethod
    def _visible_condition(actor: User):
        memberships = select(ModelProjectMembership.model_project_id).where(
            ModelProjectMembership.user_id == actor.id
        )
        return or_(
            ModelProject.created_by_id == actor.id,
            ModelProject.id.in_(memberships),
            ModelProject.system_key.is_not(None),
        )

    @staticmethod
    def _access(database, actor: User, project: ModelProject) -> AccessContext | None:
        if project.created_by_id == actor.id:
            return access_for_role("owner")
        if actor.is_system_admin:
            return administrator_access()
        membership = database.get(ModelProjectMembership, (project.id, actor.id))
        if membership is not None:
            return access_for_role(membership.role)
        if project.system_key is not None:
            return system_resource_access()
        return None

    def project_access(self, actor: User, project_id: str) -> AccessContext:
        with self._session_factory() as database:
            project = database.get(ModelProject, project_id)
            if project is None or project.deleted_at is not None:
                raise ModelNotFound("model project not found")
            access = self._access(database, actor, project)
            if access is None:
                raise ModelNotFound("model project not found")
            return access

    def can_manage(self, actor: User, project: ModelProject) -> bool:
        return self.project_access(actor, project.id).allows("project.update")

    def _require(
        self,
        database,
        actor: User,
        project: ModelProject,
        permission: Permission,
    ) -> AccessContext:
        access = self._access(database, actor, project)
        if access is None:
            raise ModelNotFound("model project not found")
        if not access.allows(permission):
            raise ModelForbidden(f"{permission} permission required")
        return access

    def list_models(self, actor: User) -> list[InferenceModel]:
        with self._session_factory() as database:
            query = (
                select(InferenceModel)
                .join(ModelProject, ModelProject.id == InferenceModel.model_project_id)
                .where(
                    InferenceModel.deleted_at.is_(None),
                    ModelProject.deleted_at.is_(None),
                )
            )
            if not actor.is_system_admin:
                query = query.where(self._visible_condition(actor))
            items = list(
                database.scalars(
                    query.order_by(InferenceModel.created_at.desc(), InferenceModel.id)
                )
            )
            for item in items:
                database.expunge(item)
            return items

    def list_projects(self, actor: User) -> list[ModelProject]:
        with self._session_factory() as database:
            query = select(ModelProject).where(ModelProject.deleted_at.is_(None))
            if not actor.is_system_admin:
                query = query.where(self._visible_condition(actor))
            items = list(
                database.scalars(
                    query.order_by(
                        case(
                            (ModelProject.system_key == OFFICIAL_YOLO11_SYSTEM_KEY, 1),
                            else_=0,
                        ),
                        ModelProject.created_at.desc(),
                        ModelProject.id,
                    )
                )
            )
            for item in items:
                database.expunge(item)
            return items

    def get_project(self, actor: User, project_id: str) -> ModelProject:
        with self._session_factory() as database:
            project = database.get(ModelProject, project_id)
            if project is None or project.deleted_at is not None:
                raise ModelNotFound("model project not found")
            if self._access(database, actor, project) is None:
                raise ModelNotFound("model project not found")
            database.expunge(project)
            return project

    def list_tags(self, actor: User) -> list[ModelProjectTag]:
        with self._session_factory() as database:
            query = (
                select(ModelProjectTag)
                .join(ModelProjectTagLink, ModelProjectTagLink.tag_id == ModelProjectTag.id)
                .join(ModelProject, ModelProject.id == ModelProjectTagLink.model_project_id)
                .where(ModelProject.deleted_at.is_(None))
                .distinct()
            )
            if not actor.is_system_admin:
                query = query.where(self._visible_condition(actor))
            items = list(database.scalars(query.order_by(ModelProjectTag.name)))
            for item in items:
                database.expunge(item)
            return items

    def project_tags(self, actor: User, project_id: str) -> list[str]:
        self.get_project(actor, project_id)
        with self._session_factory() as database:
            return list(
                database.scalars(
                    select(ModelProjectTag.name)
                    .join(ModelProjectTagLink, ModelProjectTagLink.tag_id == ModelProjectTag.id)
                    .where(ModelProjectTagLink.model_project_id == project_id)
                    .order_by(ModelProjectTag.name)
                )
            )

    @staticmethod
    def _set_tags(database, project_id: str, names: list[str]) -> None:
        clean_names = list(dict.fromkeys(_clean_text(name, 24, "tag", required=True) for name in names))
        if not 1 <= len(clean_names) <= 20:
            raise InvalidModel("model project requires 1-20 tags")
        for link in database.scalars(
            select(ModelProjectTagLink).where(ModelProjectTagLink.model_project_id == project_id)
        ):
            database.delete(link)
        database.flush()
        for name in clean_names:
            normalized = name.lower()
            tag = database.scalar(
                select(ModelProjectTag).where(ModelProjectTag.name_normalized == normalized)
            )
            if tag is None:
                tag = ModelProjectTag(
                    id=str(uuid4()),
                    name=name,
                    name_normalized=normalized,
                    created_at=_utc_now(),
                )
                database.add(tag)
                database.flush()
            database.add(ModelProjectTagLink(model_project_id=project_id, tag_id=tag.id))
        database.flush()
        ModelService._prune_unused_tags(database)

    @staticmethod
    def _prune_unused_tags(database) -> None:
        used_tag_ids = select(ModelProjectTagLink.tag_id)
        database.execute(delete(ModelProjectTag).where(ModelProjectTag.id.not_in(used_tag_ids)))

    def create_project(
        self, actor: User, name: str, description: str, tags: list[str]
    ) -> ModelProject:
        now = _utc_now()
        project = ModelProject(
            id=str(uuid4()),
            name=_clean_text(name, 128, "model project name", required=True),
            name_normalized=_normalized_name(name),
            description=_clean_text(description, 2000, "description"),
            series_type="archive",
            created_by_id=actor.id,
            version=1,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as database:
            try:
                database.add(project)
                database.flush()
                self._set_tags(database, project.id, tags)
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise ModelConflict("active model project name already exists") from exc
            database.expunge(project)
        return project

    def update_project(
        self,
        actor: User,
        project_id: str,
        *,
        name: str,
        description: str,
        tags: list[str] | None,
        version: int,
    ) -> ModelProject:
        with self._session_factory() as database:
            project = database.get(ModelProject, project_id)
            if project is None or project.deleted_at is not None:
                raise ModelNotFound("model project not found")
            self._require(database, actor, project, "project.update")
            if project.version != version:
                raise ModelConflict("model project version conflict")
            project.name = _clean_text(name, 128, "model project name", required=True)
            project.name_normalized = _normalized_name(name)
            project.description = _clean_text(description, 2000, "description")
            if tags is not None:
                self._set_tags(database, project.id, tags)
            project.version += 1
            project.updated_at = _utc_now()
            try:
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise ModelConflict("active model project name already exists") from exc
            database.expunge(project)
            return project

    def list_project_models(self, actor: User, model_project_id: str) -> list[InferenceModel]:
        self.get_project(actor, model_project_id)
        with self._session_factory() as database:
            items = list(
                database.scalars(
                    select(InferenceModel)
                    .where(
                        InferenceModel.model_project_id == model_project_id,
                        InferenceModel.deleted_at.is_(None),
                    )
                    .order_by(InferenceModel.created_at.desc(), InferenceModel.id)
                )
            )
            for item in items:
                database.expunge(item)
            return items

    def get_model(self, actor: User, model_id: str) -> InferenceModel:
        with self._session_factory() as database:
            model = database.get(InferenceModel, model_id)
            if model is None or model.deleted_at is not None:
                raise ModelNotFound("model not found")
            project = database.get(ModelProject, model.model_project_id)
            if project is None or self._access(database, actor, project) is None:
                raise ModelNotFound("model not found")
            database.expunge(model)
            return model

    def register(
        self,
        actor: User,
        model_project_id: str,
        name: str,
        source_path: str,
        description: str = "",
    ) -> RegisteredModel:
        project = self.get_project(actor, model_project_id)
        if (
            not self.project_access(actor, project.id).allows("task.execute")
            or project.series_type != "archive"
        ):
            raise ModelForbidden("model project does not accept imported models")
        clean_name = _clean_text(name, 128, "model name", required=True)
        resolver = HomePathResolver(self.settings.home)
        try:
            source = resolver.resolve_existing(source_path)
        except (OSError, UnsafePathError) as exc:
            raise InvalidModel(str(exc)) from exc
        if source == self.workspace or source.is_relative_to(self.workspace):
            raise InvalidModel("managed workspace is not an import source")
        if not source.is_file() or source.suffix.lower() not in MODEL_EXTENSIONS:
            raise InvalidModel("YOLO model source must be a .pt file")

        now = _utc_now()
        with self._session_factory() as database:
            existing = set(
                database.scalars(
                    select(InferenceModel.model_code).where(
                        InferenceModel.model_project_id == model_project_id,
                        InferenceModel.deleted_at.is_(None),
                    )
                )
            )
            base = _code(source.name)
            model_code = base
            suffix = 2
            while model_code in existing:
                model_code = f"{base[:55]}-{suffix}"
                suffix += 1
            model = InferenceModel(
                id=str(uuid4()),
                model_project_id=model_project_id,
                model_code=model_code,
                name=clean_name,
                kind="yolo",
                description=_clean_text(description, 2000, "description"),
                parameters="{}",
                status="copying",
                source_name=source.name,
                created_by_id=actor.id,
                version=1,
                created_at=now,
                updated_at=now,
            )
            task = Task(
                id=str(uuid4()),
                project_id=None,
                model_project_id=model_project_id,
                submitted_by_id=actor.id,
                type="import_model",
                payload=json.dumps(
                    {"model_id": model.id, "source_path": source_path},
                    ensure_ascii=False,
                ),
                created_at=now,
                updated_at=now,
            )
            database.add_all((model, task))
            touch_model_project(database, model_project_id, at=now)
            database.commit()
            database.expunge(model)
            database.expunge(task)
            return RegisteredModel(model, task)

    def update_model(
        self,
        actor: User,
        model_id: str,
        *,
        name: str,
        description: str,
        version: int,
        model_project_id: str | None = None,
    ) -> InferenceModel:
        with self._session_factory() as database:
            model = database.get(InferenceModel, model_id)
            if model is None or model.deleted_at is not None:
                raise ModelNotFound("model not found")
            source_project = database.get(ModelProject, model.model_project_id)
            if source_project is None:
                raise ModelNotFound("model not found")
            self._require(database, actor, source_project, "project.update")
            if source_project.series_type != "archive":
                raise ModelForbidden("model is read-only")
            if model.version != version:
                raise ModelConflict("model version conflict")
            source_project_id = source_project.id
            if model_project_id and model_project_id != model.model_project_id:
                target = database.get(ModelProject, model_project_id)
                if (
                    target is None
                    or target.deleted_at is not None
                    or target.series_type != "archive"
                ):
                    raise ModelForbidden("target model project is read-only")
                self._require(database, actor, target, "project.update")
                model.model_project_id = target.id
            model.name = _clean_text(name, 128, "model name", required=True)
            model.description = _clean_text(description, 2000, "description")
            model.version += 1
            now = _utc_now()
            model.updated_at = now
            touch_model_project(database, source_project_id, at=now)
            if model.model_project_id != source_project_id:
                touch_model_project(database, model.model_project_id, at=now)
            try:
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise ModelConflict("model code already exists in target project") from exc
            database.expunge(model)
            return model

    def delete_model(self, actor: User, model_id: str) -> None:
        now = _utc_now()
        source = self.workspace / "models" / model_id
        destination = self.workspace / ".deleted" / "models" / model_id
        with self._session_factory() as database:
            model = database.get(InferenceModel, model_id)
            if model is None or model.deleted_at is not None:
                raise ModelNotFound("model not found")
            project = database.get(ModelProject, model.model_project_id)
            if project is None:
                raise ModelNotFound("model not found")
            self._require(database, actor, project, "project.update")
            if self._model_in_use(database, model.id):
                raise ModelConflict("model has active tasks")
            if destination.exists():
                raise ModelConflict("model archive already exists")
            moved = False
            try:
                if source.exists():
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(source, destination)
                    moved = True
                model.deleted_at = now
                model.updated_at = now
                model.version += 1
                self._delete_model_capabilities(database, model.id, now)
                touch_model_project(database, model.model_project_id, at=now)
                database.commit()
            except Exception:
                database.rollback()
                if moved and destination.exists():
                    source.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(destination, source)
                raise

    def delete_project(self, actor: User, project_id: str) -> None:
        now = _utc_now()
        archive = self.workspace / ".deleted" / "model-projects" / project_id
        with self._session_factory() as database:
            project = database.get(ModelProject, project_id)
            if project is None or project.deleted_at is not None:
                raise ModelNotFound("model project not found")
            self._require(database, actor, project, "project.delete")
            if project.system_key is not None:
                raise ModelForbidden("model project is read-only")
            models = list(
                database.scalars(
                    select(InferenceModel).where(
                        InferenceModel.model_project_id == project_id,
                        InferenceModel.deleted_at.is_(None),
                    )
                )
            )
            if any(self._model_in_use(database, model.id) for model in models):
                raise ModelConflict("model project has active model tasks")
            if database.scalar(
                select(Task).where(
                    Task.model_project_id == project_id,
                    Task.status.in_(("queued", "running")),
                )
            ):
                raise ModelConflict("model project has active tasks")
            if archive.exists():
                raise ModelConflict("model project archive already exists")
            moved: list[tuple[Path, Path]] = []
            try:
                archive.mkdir(parents=True)
                for model in models:
                    source = self.workspace / "models" / model.id
                    target = archive / "models" / model.id
                    if source.exists():
                        target.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(source, target)
                        moved.append((source, target))
                    model.deleted_at = now
                    model.updated_at = now
                    model.version += 1
                    self._delete_model_capabilities(database, model.id, now)
                project_data = self.workspace / "model-projects" / project_id
                if project_data.exists():
                    project_target = archive / "project-data"
                    os.replace(project_data, project_target)
                    moved.append((project_data, project_target))
                (archive / "metadata.json").write_text(
                    json.dumps(
                        {
                            "format_version": 1,
                            "project_id": project.id,
                            "name": project.name,
                            "models": [model.id for model in models],
                            "deleted_at": now.isoformat(),
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                project.deleted_at = now
                project.updated_at = now
                project.version += 1
                database.execute(
                    delete(ModelProjectTagLink).where(
                        ModelProjectTagLink.model_project_id == project.id
                    )
                )
                database.flush()
                self._prune_unused_tags(database)
                database.commit()
            except Exception:
                database.rollback()
                for source, target in reversed(moved):
                    source.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target, source)
                shutil.rmtree(archive, ignore_errors=True)
                raise

    def list_members(self, actor: User, project_id: str) -> list[ModelMemberView]:
        with self._session_factory() as database:
            project = database.get(ModelProject, project_id)
            if project is None or project.deleted_at is not None:
                raise ModelNotFound("model project not found")
            self._require(database, actor, project, "project.read")
            members: list[ModelMemberView] = []
            if project.created_by_id is not None:
                owner = database.get(User, project.created_by_id)
                if owner is not None:
                    members.append(ModelMemberView(owner, "owner", project.created_at))
            rows = database.execute(
                select(ModelProjectMembership, User)
                .join(User, User.id == ModelProjectMembership.user_id)
                .where(ModelProjectMembership.model_project_id == project_id)
                .order_by(User.username_normalized)
            )
            members.extend(
                ModelMemberView(user, membership.role, membership.created_at)
                for membership, user in rows
            )
            return members

    def add_member(
        self, actor: User, project_id: str, username: str, role: str
    ) -> ModelMemberView:
        if role not in {"editor", "viewer"}:
            raise InvalidModelMember("role must be editor or viewer")
        try:
            normalized = normalize_username(username)
        except ValueError:
            raise InvalidModelMember("active user not found") from None
        with self._session_factory() as database:
            project = database.get(ModelProject, project_id)
            if project is None or project.deleted_at is not None:
                raise ModelNotFound("model project not found")
            self._require(database, actor, project, "project.members.manage")
            if project.system_key is not None:
                raise ModelForbidden(
                    "system model projects do not accept explicit members"
                )
            user = database.scalar(
                select(User).where(User.username_normalized == normalized)
            )
            if user is None or user.status != "active" or user.is_system_admin:
                raise InvalidModelMember("active user not found")
            if user.id == project.created_by_id:
                raise InvalidModelMember("model project creator is already the owner")
            now = _utc_now()
            membership = ModelProjectMembership(
                model_project_id=project_id,
                user_id=user.id,
                role=role,
                created_at=now,
            )
            try:
                database.add(membership)
                touch_model_project(database, project_id, at=now)
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise ModelConflict("user is already a model project member") from exc
            return ModelMemberView(user, role, membership.created_at)

    def change_member_role(
        self, actor: User, project_id: str, user_id: str, role: str
    ) -> ModelMemberView:
        if role not in {"editor", "viewer"}:
            raise InvalidModelMember("role must be editor or viewer")
        with self._session_factory() as database:
            project = database.get(ModelProject, project_id)
            if project is None or project.deleted_at is not None:
                raise ModelNotFound("model project not found")
            self._require(database, actor, project, "project.members.manage")
            if project.system_key is not None:
                raise ModelForbidden(
                    "system model projects do not accept explicit members"
                )
            if user_id == project.created_by_id:
                raise InvalidModelMember("model project owner cannot be changed")
            membership = database.get(ModelProjectMembership, (project_id, user_id))
            user = database.get(User, user_id)
            if membership is None or user is None:
                raise InvalidModelMember("model project member not found")
            membership.role = role
            touch_model_project(database, project_id, at=_utc_now())
            database.commit()
            return ModelMemberView(user, role, membership.created_at)

    def remove_member(self, actor: User, project_id: str, user_id: str) -> None:
        with self._session_factory() as database:
            project = database.get(ModelProject, project_id)
            if project is None or project.deleted_at is not None:
                raise ModelNotFound("model project not found")
            self._require(database, actor, project, "project.members.manage")
            if project.system_key is not None:
                raise ModelForbidden(
                    "system model projects do not accept explicit members"
                )
            if user_id == project.created_by_id:
                raise InvalidModelMember("model project owner cannot be removed")
            membership = database.get(ModelProjectMembership, (project_id, user_id))
            if membership is None:
                raise InvalidModelMember("model project member not found")
            database.delete(membership)
            touch_model_project(database, project_id, at=_utc_now())
            database.commit()

    @staticmethod
    def _model_in_use(database, model_id: str) -> bool:
        tasks = database.scalars(
            select(Task).where(Task.status.in_(("queued", "running")))
        )
        for task in tasks:
            try:
                payload = json.loads(task.payload)
                if task.type in {"auto_annotate", "convert_model"} and payload.get("model_id") == model_id:
                    return True
                if task.type == "infer_video":
                    run = database.get(ModelInferenceRun, payload.get("run_id"))
                    if run is not None and run.model_id == model_id:
                        return True
                if task.type == "evaluate_model":
                    evaluation = database.get(ModelEvaluation, payload.get("evaluation_id"))
                    if evaluation is not None and evaluation.model_id == model_id:
                        return True
            except (TypeError, ValueError):
                continue
        return False

    @staticmethod
    def _delete_model_capabilities(database, model_id: str, now: datetime) -> None:
        for artifact in database.scalars(
            select(ModelArtifact).where(
                ModelArtifact.model_id == model_id,
                ModelArtifact.deleted_at.is_(None),
            )
        ):
            artifact.deleted_at = now
            artifact.updated_at = now
        for run in database.scalars(
            select(ModelInferenceRun).where(
                ModelInferenceRun.model_id == model_id,
                ModelInferenceRun.deleted_at.is_(None),
            )
        ):
            run.deleted_at = now

    def ready_model(
        self,
        actor: User,
        model_id: str,
        permission: Permission = "artifact.download",
    ) -> tuple[InferenceModel, Path]:
        with self._session_factory() as database:
            model = database.get(InferenceModel, model_id)
            if model is None or model.deleted_at is not None:
                raise ModelNotFound("model not found")
            project = database.get(ModelProject, model.model_project_id)
            if project is None:
                raise ModelNotFound("model not found")
            self._require(database, actor, project, permission)
            if model.status != "ready" or not model.storage_path:
                raise InvalidModel("model is not ready")
            try:
                path = (self.workspace / model.storage_path).resolve(strict=True)
            except OSError as exc:
                raise ModelNotFound("model file not found") from exc
            root = (self.workspace / "models" / model.id).resolve()
            if not path.is_file() or not path.is_relative_to(root):
                raise ModelNotFound("model file not found")
            database.expunge(model)
            return model, path
