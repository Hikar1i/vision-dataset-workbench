import json
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..capabilities import SystemCapabilities
from ..models import InferenceModel, ModelArtifact, ModelProject, Task, User


class ModelArtifactNotFound(ValueError):
    pass


class ModelArtifactForbidden(ValueError):
    pass


class ModelArtifactConflict(ValueError):
    pass


class InvalidModelArtifact(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def default_runtime_fingerprint() -> dict[str, object]:
    try:
        import tensorrt
        import torch
    except (ImportError, OSError):
        return {}
    return {
        "tensorrt": str(tensorrt.__version__),
        "cuda_runtime": str(torch.version.cuda or ""),
    }


class ModelArtifactService:
    def __init__(
        self,
        engine: Engine,
        workspace: Path,
        capabilities: SystemCapabilities,
        *,
        fingerprint: Callable[[], dict[str, object]] = default_runtime_fingerprint,
    ):
        self.workspace = workspace.resolve()
        self.capabilities = capabilities
        self._fingerprint = fingerprint
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    @staticmethod
    def _can_manage(actor: User, project: ModelProject) -> bool:
        return project.system_key is None and (
            actor.is_system_admin or project.created_by_id == actor.id
        )

    def list(self, actor: User, model_id: str) -> list[ModelArtifact]:
        with self._session_factory() as database:
            model = self._model(database, model_id)
            rows = list(
                database.scalars(
                    select(ModelArtifact)
                    .where(
                        ModelArtifact.model_id == model.id,
                        ModelArtifact.deleted_at.is_(None),
                    )
                    .order_by(ModelArtifact.format)
                )
            )
            changed = False
            for row in rows:
                changed |= self._mark_stale(row, model)
            if changed:
                database.commit()
            for row in rows:
                database.expunge(row)
            return rows

    def create(
        self,
        actor: User,
        model_id: str,
        artifact_format: str,
        *,
        image_size: int = 640,
        dynamic: bool = False,
        precision: str = "fp16",
    ) -> tuple[ModelArtifact, Task]:
        if artifact_format not in {"onnx", "engine"}:
            raise InvalidModelArtifact("unsupported model format")
        if image_size < 32 or image_size > 8192 or image_size % 32:
            raise InvalidModelArtifact("image size must be 32-8192 and divisible by 32")
        if artifact_format == "engine" and dynamic:
            raise InvalidModelArtifact("TensorRT only supports fixed batch 1")
        if precision not in {"fp16", "fp32"}:
            raise InvalidModelArtifact("precision must be fp16 or fp32")
        capability = (
            self.capabilities.features.onnx_export
            if artifact_format == "onnx"
            else self.capabilities.features.tensorrt
        )
        if not capability.available:
            raise ModelArtifactConflict(capability.reason or "model conversion unavailable")
        now = _now()
        with self._session_factory() as database:
            model = self._model(database, model_id)
            project = database.get(ModelProject, model.model_project_id)
            if project is None or not self._can_manage(actor, project):
                raise ModelArtifactForbidden("model project is read-only")
            if not model.sha256:
                raise InvalidModelArtifact("model source hash is unavailable")
            config = {
                "imgsz": image_size,
                "batch": 1,
                "dynamic": dynamic if artifact_format == "onnx" else False,
                "simplify": artifact_format == "onnx",
                "nms": False,
                "precision": precision if artifact_format == "engine" else None,
            }
            artifact = ModelArtifact(
                id=str(uuid4()),
                model_id=model.id,
                format=artifact_format,
                status="queued",
                source_model_sha256=model.sha256,
                export_config=json.dumps(config, ensure_ascii=False),
                created_by_id=actor.id,
                created_at=now,
                updated_at=now,
            )
            task = Task(
                id=str(uuid4()),
                model_project_id=model.model_project_id,
                submitted_by_id=actor.id,
                type="convert_model",
                payload=json.dumps(
                    {
                        "artifact_id": artifact.id,
                        "model_id": model.id,
                        "source_model_sha256": model.sha256,
                    },
                    ensure_ascii=False,
                ),
                created_at=now,
                updated_at=now,
            )
            artifact.task_id = task.id
            try:
                database.add(task)
                database.flush()
                database.add(artifact)
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise ModelArtifactConflict("model format already exists") from exc
            database.expunge(artifact)
            database.expunge(task)
            return artifact, task

    def downloadable(self, actor: User, artifact_id: str) -> tuple[ModelArtifact, Path, str]:
        with self._session_factory() as database:
            artifact = database.get(ModelArtifact, artifact_id)
            if artifact is None or artifact.deleted_at is not None:
                raise ModelArtifactNotFound("model artifact not found")
            model = self._model(database, artifact.model_id)
            if self._mark_stale(artifact, model):
                database.commit()
            if artifact.status != "ready" or not artifact.storage_path:
                raise ModelArtifactConflict("model artifact is not ready")
            path = (self.workspace / artifact.storage_path).resolve()
            root = (self.workspace / "models" / model.id / "artifacts").resolve()
            if not path.is_file() or not path.is_relative_to(root):
                raise ModelArtifactNotFound("model artifact file not found")
            database.expunge(artifact)
            return artifact, path, model.model_code

    def delete(self, actor: User, artifact_id: str) -> None:
        now = _now()
        with self._session_factory() as database:
            artifact = database.get(ModelArtifact, artifact_id)
            if artifact is None or artifact.deleted_at is not None:
                raise ModelArtifactNotFound("model artifact not found")
            model = self._model(database, artifact.model_id)
            project = database.get(ModelProject, model.model_project_id)
            if project is None or not self._can_manage(actor, project):
                raise ModelArtifactForbidden("model project is read-only")
            active = list(
                database.scalars(
                    select(Task).where(Task.status.in_(("queued", "running")))
                )
            )
            if any(self._task_references(item, artifact.id) for item in active):
                raise ModelArtifactConflict("model artifact is used by an active task")
            if artifact.storage_path:
                path = (self.workspace / artifact.storage_path).resolve()
                root = (self.workspace / "models" / model.id / "artifacts").resolve()
                if path.is_file() and path.is_relative_to(root):
                    path.unlink()
            artifact.deleted_at = now
            artifact.updated_at = now
            database.commit()

    def invalidate_model(self, database, model: InferenceModel) -> None:
        for artifact in database.scalars(
            select(ModelArtifact).where(
                ModelArtifact.model_id == model.id,
                ModelArtifact.deleted_at.is_(None),
                ModelArtifact.status != "stale",
            )
        ):
            if artifact.source_model_sha256 != model.sha256:
                artifact.status = "stale"
                artifact.error = "源模型已更新，请删除后重新转换"
                artifact.updated_at = _now()

    def _mark_stale(self, artifact: ModelArtifact, model: InferenceModel) -> bool:
        reason = None
        if artifact.source_model_sha256 != model.sha256:
            reason = "源模型已更新，请删除后重新转换"
        elif artifact.format == "engine" and artifact.status == "ready":
            expected = json.loads(artifact.environment_fingerprint or "{}")
            current = self._fingerprint()
            device = next(
                (item for item in self.capabilities.gpu.devices if item.uuid == artifact.gpu_uuid),
                None,
            )
            current.update(
                {
                    "gpu_uuid": device.uuid if device else None,
                    "compute_capability": device.compute_capability if device else None,
                }
            )
            for key in ("gpu_uuid", "compute_capability", "tensorrt"):
                if expected.get(key) != current.get(key):
                    reason = "TensorRT 运行环境与构建环境不一致"
                    break
            if reason is None and self._major_minor(expected.get("cuda_runtime")) != self._major_minor(
                current.get("cuda_runtime")
            ):
                reason = "TensorRT 运行环境与构建环境不一致"
        if reason is None or artifact.status == "stale":
            return False
        artifact.status = "stale"
        artifact.error = reason
        artifact.updated_at = _now()
        return True

    @staticmethod
    def _task_references(task: Task, artifact_id: str) -> bool:
        try:
            return json.loads(task.payload).get("artifact_id") == artifact_id
        except (TypeError, ValueError):
            return False

    @staticmethod
    def _major_minor(value: object) -> tuple[str, str] | None:
        parts = str(value or "").split(".")
        return (parts[0], parts[1]) if len(parts) >= 2 else None

    @staticmethod
    def _model(database, model_id: str) -> InferenceModel:
        model = database.get(InferenceModel, model_id)
        if model is None or model.deleted_at is not None:
            raise ModelArtifactNotFound("model not found")
        if model.status != "ready" or not model.storage_path:
            raise InvalidModelArtifact("model is not ready")
        return model
