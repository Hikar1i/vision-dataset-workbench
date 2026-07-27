import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..config import RuntimeSettings
from ..models import InferenceModel, Task, User
from ..storage.browser import MODEL_EXTENSIONS
from ..storage.paths import HomePathResolver, UnsafePathError
from .projects import ProjectService


class ModelNotFound(ValueError):
    pass


class ModelForbidden(ValueError):
    pass


class InvalidModel(ValueError):
    pass


@dataclass(frozen=True)
class RegisteredModel:
    model: InferenceModel
    task: Task


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


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

    def list_models(self, actor: User) -> list[InferenceModel]:
        with self._session_factory() as database:
            items = list(
                database.scalars(
                    select(InferenceModel).order_by(
                        InferenceModel.created_at.desc(), InferenceModel.id
                    )
                )
            )
            for item in items:
                database.expunge(item)
            return items

    def register(
        self,
        actor: User,
        project_id: str,
        name: str,
        kind: str,
        source_path: str,
    ) -> RegisteredModel:
        if not actor.is_system_admin:
            raise ModelForbidden("system administrator permission required")
        self.projects.get_project(actor, project_id)
        clean_name = " ".join(name.strip().split())
        if not clean_name or len(clean_name) > 128:
            raise InvalidModel("model name must contain 1-128 characters")
        if kind not in {"yolo", "grounding_dino"}:
            raise InvalidModel("model kind is invalid")
        resolver = HomePathResolver(self.settings.home)
        try:
            source = resolver.resolve_existing(source_path)
        except (OSError, UnsafePathError) as exc:
            raise InvalidModel(str(exc)) from exc
        if source == self.workspace or source.is_relative_to(self.workspace):
            raise InvalidModel("managed workspace is not an import source")
        if kind == "yolo" and (
            not source.is_file() or source.suffix.lower() not in MODEL_EXTENSIONS
        ):
            raise InvalidModel("YOLO model source must be a .pt or .onnx file")
        if kind == "grounding_dino" and not source.is_dir():
            raise InvalidModel("GroundingDINO model source must be a local model directory")

        now = _utc_now()
        model = InferenceModel(
            id=str(uuid4()),
            name=clean_name,
            kind=kind,
            status="copying",
            source_name=source.name,
            created_by_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        task = Task(
            id=str(uuid4()),
            project_id=project_id,
            submitted_by_id=actor.id,
            type="import_model",
            payload=json.dumps(
                {"model_id": model.id, "source_path": source_path},
                ensure_ascii=False,
            ),
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as database:
            database.add(model)
            database.add(task)
            database.commit()
            database.expunge(model)
            database.expunge(task)
        return RegisteredModel(model, task)

    def ready_model(self, model_id: str) -> tuple[InferenceModel, Path]:
        with self._session_factory() as database:
            model = database.get(InferenceModel, model_id)
            if model is None:
                raise ModelNotFound("model not found")
            if model.status != "ready" or not model.storage_path:
                raise InvalidModel("model is not ready")
            try:
                path = (self.workspace / model.storage_path).resolve(strict=True)
            except OSError as exc:
                raise ModelNotFound("model file not found") from exc
            root = (self.workspace / "models" / model.id).resolve()
            if not path.is_relative_to(root):
                raise ModelNotFound("model file not found")
            database.expunge(model)
            return model, path
