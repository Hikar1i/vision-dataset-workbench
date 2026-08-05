import json
import os
import re
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..config import RuntimeSettings
from ..models import InferenceModel, ModelProject, Task, User
from ..storage.browser import MODEL_EXTENSIONS
from ..storage.paths import HomePathResolver, UnsafePathError
from .projects import ProjectService


class ModelNotFound(ValueError):
    pass


class ModelForbidden(ValueError):
    pass


class ModelConflict(ValueError):
    pass


class InvalidModel(ValueError):
    pass


@dataclass(frozen=True)
class RegisteredModel:
    model: InferenceModel
    task: Task


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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
    def can_manage(actor: User, project: ModelProject) -> bool:
        return project.system_key is None and (
            actor.is_system_admin or project.created_by_id == actor.id
        )

    def list_models(self, actor: User) -> list[InferenceModel]:
        with self._session_factory() as database:
            items = list(
                database.scalars(
                    select(InferenceModel)
                    .where(InferenceModel.deleted_at.is_(None))
                    .order_by(InferenceModel.created_at.desc(), InferenceModel.id)
                )
            )
            for item in items:
                database.expunge(item)
            return items

    def list_projects(self, actor: User) -> list[ModelProject]:
        with self._session_factory() as database:
            items = list(
                database.scalars(
                    select(ModelProject)
                    .where(ModelProject.deleted_at.is_(None))
                    .order_by(ModelProject.updated_at.desc(), ModelProject.id)
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
            database.expunge(project)
            return project

    def create_project(self, actor: User, name: str, description: str) -> ModelProject:
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
        version: int,
    ) -> ModelProject:
        with self._session_factory() as database:
            project = database.get(ModelProject, project_id)
            if project is None or project.deleted_at is not None:
                raise ModelNotFound("model project not found")
            if not self.can_manage(actor, project):
                raise ModelForbidden("model project is read-only")
            if project.version != version:
                raise ModelConflict("model project version conflict")
            project.name = _clean_text(name, 128, "model project name", required=True)
            project.name_normalized = _normalized_name(name)
            project.description = _clean_text(description, 2000, "description")
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
        if not self.can_manage(actor, project) or project.series_type != "archive":
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
            if source_project is None or not self.can_manage(actor, source_project):
                raise ModelForbidden("model is read-only")
            if source_project.series_type != "archive" or source_project.system_key is not None:
                raise ModelForbidden("model is read-only")
            if model.version != version:
                raise ModelConflict("model version conflict")
            if model_project_id and model_project_id != model.model_project_id:
                target = database.get(ModelProject, model_project_id)
                if (
                    target is None
                    or target.deleted_at is not None
                    or target.series_type != "archive"
                    or not self.can_manage(actor, target)
                ):
                    raise ModelForbidden("target model project is read-only")
                model.model_project_id = target.id
            model.name = _clean_text(name, 128, "model name", required=True)
            model.description = _clean_text(description, 2000, "description")
            model.version += 1
            model.updated_at = _utc_now()
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
            if project is None or not self.can_manage(actor, project):
                raise ModelForbidden("model is read-only")
            if self._model_in_use(database, model.id):
                raise ModelConflict("model has active annotation tasks")
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
            if not self.can_manage(actor, project):
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
                raise ModelConflict("model project has active annotation tasks")
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
                database.commit()
            except Exception:
                database.rollback()
                for source, target in reversed(moved):
                    source.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(target, source)
                shutil.rmtree(archive, ignore_errors=True)
                raise

    @staticmethod
    def _model_in_use(database, model_id: str) -> bool:
        tasks = database.scalars(
            select(Task).where(Task.type == "auto_annotate", Task.status.in_(("queued", "running")))
        )
        for task in tasks:
            try:
                if json.loads(task.payload).get("model_id") == model_id:
                    return True
            except (TypeError, ValueError):
                continue
        return False

    def ready_model(self, model_id: str) -> tuple[InferenceModel, Path]:
        with self._session_factory() as database:
            model = database.get(InferenceModel, model_id)
            if model is None or model.deleted_at is not None:
                raise ModelNotFound("model not found")
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
