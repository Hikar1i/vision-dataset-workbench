import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..models import (
    EvaluationDataset,
    InferenceModel,
    ModelArtifact,
    ModelEvaluation,
    ModelProject,
    Task,
    User,
)
from .authorization import Permission
from .models import ModelNotFound, ModelService, touch_model_project

ZIP_LIMIT = 1024 * 1024 * 1024


class ModelEvaluationError(ValueError):
    pass


class ModelEvaluationNotFound(ModelEvaluationError):
    pass


class ModelEvaluationForbidden(ModelEvaluationError):
    pass


class ModelEvaluationConflict(ModelEvaluationError):
    pass


def _now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ModelEvaluationService:
    def __init__(
        self,
        engine: Engine,
        workspace: Path,
        artifact_service=None,
        models: ModelService | None = None,
    ):
        self.workspace = workspace.resolve()
        self.artifact_service = artifact_service
        self.models = models
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def _require(self, actor: User, project_id: str, permission: Permission) -> None:
        if self.models is None:
            raise ModelEvaluationForbidden("model authorization is unavailable")
        try:
            access = self.models.project_access(actor, project_id)
        except ModelNotFound as exc:
            raise ModelEvaluationNotFound("模型项目不存在") from exc
        if not access.allows(permission):
            raise ModelEvaluationForbidden(f"{permission} permission required")

    def require_manage(self, actor: User, project_id: str) -> None:
        self._require(actor, project_id, "task.execute")

    def list_datasets(self, actor: User, project_id: str):
        self._require(actor, project_id, "artifact.read")
        with self._session_factory() as database:
            self._project(database, project_id)
            rows = list(
                database.scalars(
                    select(EvaluationDataset)
                    .where(
                        EvaluationDataset.model_project_id == project_id,
                        EvaluationDataset.deleted_at.is_(None),
                    )
                    .order_by(EvaluationDataset.created_at.desc())
                )
            )
            for row in rows:
                database.expunge(row)
            return rows

    def create_dataset(self, actor: User, project_id: str, name: str, upload: Path):
        self._require(actor, project_id, "task.execute")
        if not name.strip() or len(name.strip()) > 128:
            raise ModelEvaluationError("测试集名称长度必须为 1 到 128")
        if not upload.is_file() or upload.stat().st_size == 0 or upload.stat().st_size > ZIP_LIMIT:
            raise ModelEvaluationError("ZIP 必须非空且不超过 1 GB")
        now = _now()
        with self._session_factory() as database:
            project = self._project(database, project_id)
            dataset = EvaluationDataset(
                id=str(uuid4()),
                model_project_id=project.id,
                name=name.strip(),
                storage_path="pending",
                status="queued",
                created_by_id=actor.id,
                created_at=now,
            )
            task = Task(
                id=str(uuid4()),
                model_project_id=project.id,
                submitted_by_id=actor.id,
                type="import_evaluation_dataset",
                payload=json.dumps({"dataset_id": dataset.id}),
                created_at=now,
                updated_at=now,
            )
            database.add(task)
            database.flush()
            dataset.task_id = task.id
            staging = self.workspace / "tmp" / "evaluation-uploads" / f"{dataset.id}.zip"
            staging.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(upload), staging)
            dataset.storage_path = staging.relative_to(self.workspace).as_posix()
            database.add(dataset)
            touch_model_project(database, project.id, at=now)
            database.commit()
            database.expunge(dataset)
            database.expunge(task)
            return dataset, task

    def delete_dataset(self, actor: User, dataset_id: str):
        now = _now()
        with self._session_factory() as database:
            dataset = self._dataset(database, dataset_id)
            project = self._project(database, dataset.model_project_id)
            self._require(actor, project.id, "project.update")
            active = database.scalar(
                select(ModelEvaluation).where(
                    ModelEvaluation.evaluation_dataset_id == dataset.id,
                    ModelEvaluation.status.in_(("queued", "running")),
                )
            )
            if active:
                raise ModelEvaluationConflict("测试集正在被评估任务使用")
            dataset.deleted_at = now
            touch_model_project(database, project.id, at=now)
            database.commit()
            if dataset.storage_path:
                path = (self.workspace / dataset.storage_path).resolve()
                managed_root = (self.workspace / "model-projects").resolve()
                staging_root = (self.workspace / "tmp" / "evaluation-uploads").resolve()
                if path.is_file() and path.is_relative_to(staging_root):
                    path.unlink()
                elif path.exists() and path.is_relative_to(managed_root):
                    trash = (
                        self.workspace
                        / ".deleted"
                        / "model-projects"
                        / dataset.model_project_id
                        / "evaluation-datasets"
                        / dataset.id
                    )
                    trash.parent.mkdir(parents=True, exist_ok=True)
                    if trash.exists():
                        shutil.rmtree(trash)
                    shutil.move(str(path), trash)

    def list_evaluations(self, actor: User, project_id: str):
        self._require(actor, project_id, "artifact.read")
        with self._session_factory() as database:
            self._project(database, project_id)
            rows = list(
                database.scalars(
                    select(ModelEvaluation)
                    .where(ModelEvaluation.model_project_id == project_id)
                    .order_by(ModelEvaluation.created_at.desc())
                )
            )
            for row in rows:
                database.expunge(row)
            return rows

    def create_evaluation(
        self, actor: User, project_id: str, model_id: str, dataset_id: str, artifact_format: str
    ):
        self._require(actor, project_id, "artifact.consume")
        self._require(actor, project_id, "task.execute")
        if artifact_format not in {"pt", "onnx", "engine"}:
            raise ModelEvaluationError("不支持的模型格式")
        now = _now()
        with self._session_factory() as database:
            project = self._project(database, project_id)
            model = database.get(InferenceModel, model_id)
            dataset = self._dataset(database, dataset_id)
            if (
                model is None
                or model.model_project_id != project.id
                or model.status != "ready"
                or dataset.model_project_id != project.id
                or dataset.status != "ready"
            ):
                raise ModelEvaluationError("模型或测试集不可用")
            artifact_hash = None
            if artifact_format != "pt":
                if self.artifact_service is not None:
                    self.artifact_service.list(actor, model.id)
                artifact = database.scalar(
                    select(ModelArtifact).where(
                        ModelArtifact.model_id == model.id,
                        ModelArtifact.format == artifact_format,
                        ModelArtifact.status == "ready",
                        ModelArtifact.deleted_at.is_(None),
                    )
                )
                if artifact is None:
                    raise ModelEvaluationConflict("所选格式尚无可用转换产物")
                artifact_hash = artifact.sha256
            evaluation = ModelEvaluation(
                id=str(uuid4()),
                model_project_id=project.id,
                model_id=model.id,
                model_name=model.name,
                source_model_sha256=model.sha256 or "",
                format=artifact_format,
                artifact_sha256=artifact_hash,
                evaluation_dataset_id=dataset.id,
                dataset_name=dataset.name,
                dataset_sha256=dataset.content_sha256 or "",
                config=json.dumps({"conf": 0.001, "iou": 0.70, "batch": 1, "max_det": 300}),
                status="queued",
                created_by_id=actor.id,
                created_at=now,
            )
            task = Task(
                id=str(uuid4()),
                model_project_id=project.id,
                submitted_by_id=actor.id,
                type="evaluate_model",
                payload=json.dumps({"evaluation_id": evaluation.id}),
                created_at=now,
                updated_at=now,
            )
            database.add(task)
            database.flush()
            evaluation.task_id = task.id
            database.add(evaluation)
            touch_model_project(database, project.id, at=now)
            database.commit()
            database.expunge(evaluation)
            database.expunge(task)
            return evaluation, task

    def get_evaluation(self, actor: User, evaluation_id: str):
        with self._session_factory() as database:
            row = database.get(ModelEvaluation, evaluation_id)
            if row is None:
                raise ModelEvaluationNotFound("评估记录不存在")
            self._project(database, row.model_project_id)
            self._require(actor, row.model_project_id, "artifact.read")
            database.expunge(row)
            return row

    def peak_model_metric(self, model_id: str) -> dict[str, object] | None:
        with self._session_factory() as database:
            rows = database.scalars(
                select(ModelEvaluation)
                .where(
                    ModelEvaluation.model_id == model_id,
                    ModelEvaluation.status == "succeeded",
                )
                .order_by(ModelEvaluation.finished_at.desc(), ModelEvaluation.id.desc())
            ).all()
            if not rows:
                return None
            row = max(
                rows,
                key=lambda item: float(json.loads(item.metrics)["map50_95"]),
            )
            metrics = json.loads(row.metrics)
            return {
                "id": row.id,
                "map50_95": metrics.get("map50_95"),
                "format": row.format,
                "dataset_name": row.dataset_name,
                "dataset_hash": row.dataset_sha256,
            }

    def evaluation_availability(self, evaluation: ModelEvaluation) -> dict[str, bool]:
        with self._session_factory() as database:
            model = database.get(InferenceModel, evaluation.model_id)
            dataset = database.get(EvaluationDataset, evaluation.evaluation_dataset_id)
            return {
                "model_deleted": model is None or model.deleted_at is not None,
                "dataset_deleted": dataset is None or dataset.deleted_at is not None,
            }

    def cancel(self, actor: User, evaluation_id: str):
        with self._session_factory() as database:
            row = database.get(ModelEvaluation, evaluation_id)
            if row is None:
                raise ModelEvaluationNotFound("评估记录不存在")
            self._project(database, row.model_project_id)
            self._require(actor, row.model_project_id, "task.execute")
            if row.status not in {"queued", "running"}:
                raise ModelEvaluationConflict("评估任务已结束")
            task = database.get(Task, row.task_id) if row.task_id else None
            if task:
                task.cancel_requested = True
            touch_model_project(database, row.model_project_id, at=_now())
            database.commit()

    def result_file(self, actor: User, evaluation_id: str, kind: str):
        row = self.get_evaluation(actor, evaluation_id)
        relative = row.confusion_matrix_path if kind == "confusion" else row.pr_curve_path
        if not relative:
            raise ModelEvaluationNotFound("评估图表不存在")
        path = (self.workspace / relative).resolve()
        root = (
            self.workspace / "model-projects" / row.model_project_id / "evaluations" / row.id
        ).resolve()
        if not path.is_file() or not path.is_relative_to(root):
            raise ModelEvaluationNotFound("评估图表不存在")
        return path

    @staticmethod
    def _project(database, project_id):
        project = database.get(ModelProject, project_id)
        if project is None or project.deleted_at is not None:
            raise ModelEvaluationNotFound("模型项目不存在")
        return project

    @staticmethod
    def _dataset(database, dataset_id):
        dataset = database.get(EvaluationDataset, dataset_id)
        if dataset is None or dataset.deleted_at is not None:
            raise ModelEvaluationNotFound("测试集不存在")
        return dataset
