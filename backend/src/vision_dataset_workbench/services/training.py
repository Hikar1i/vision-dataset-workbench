import json
import secrets
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..models import (
    DatasetExport,
    HyperparameterTemplate,
    InferenceModel,
    Project,
    TrainingActionRequest,
    TrainingMetric,
    TrainingModel,
    TrainingPreparation,
    TrainingRun,
    TrainingTask,
    User,
)
from ..training.actions import model_actions, task_actions
from ..training.dataset_preparation import (
    normalize_multi_dataset_config,
    snapshot_hash,
    source_classes,
)
from ..training.hyperparameters import (
    HyperparameterValidationError,
    effective_parameters,
    validate_values,
)
from ..training.naming import build_artifact_code, validate_task_code

ACTIVE = {"preparing", "queued", "running", "canceling"}


class TrainingNotFound(ValueError):
    pass


class TrainingForbidden(ValueError):
    pass


class TrainingConflict(ValueError):
    pass


class InvalidTraining(ValueError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _clean(value: str, maximum: int, required: bool = False) -> str:
    result = " ".join(value.strip().split())
    if (required and not result) or len(result) > maximum:
        raise InvalidTraining("invalid text field")
    return result


def _config_json(value: object | None) -> str | None:
    if value is None:
        return None
    try:
        normalized = normalize_multi_dataset_config(value)
    except ValueError as exc:
        raise InvalidTraining(str(exc)) from exc
    return json.dumps(normalized, ensure_ascii=False)


def _dataset_mode(value: object, dataset_id: object) -> str:
    if value is None:
        return "single" if dataset_id else "inherit"
    mode = str(value)
    if mode not in {"inherit", "single", "multi"}:
        raise InvalidTraining("invalid model dataset mode")
    return mode


class TrainingService:
    def __init__(self, engine: Engine, workspace: Path):
        self.workspace = workspace.resolve()
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    @staticmethod
    def can_manage(actor: User, task: TrainingTask) -> bool:
        return actor.is_system_admin or task.created_by_id == actor.id

    def list_tasks(self, actor: User) -> list[TrainingTask]:
        with self._session_factory() as db:
            items = list(
                db.scalars(
                    select(TrainingTask)
                    .where(TrainingTask.deleted_at.is_(None))
                    .order_by(
                        TrainingTask.last_run_at.desc().nullslast(), TrainingTask.created_at.desc()
                    )
                )
            )
            for item in items:
                db.expunge(item)
            return items

    def get_task(self, actor: User, task_id: str) -> TrainingTask:
        with self._session_factory() as db:
            item = db.get(TrainingTask, task_id)
            if item is None or item.deleted_at is not None:
                raise TrainingNotFound("training task not found")
            db.expunge(item)
            return item

    def task_models(self, task_id: str) -> list[TrainingModel]:
        with self._session_factory() as db:
            items = list(
                db.scalars(
                    select(TrainingModel)
                    .where(
                        TrainingModel.training_task_id == task_id,
                        TrainingModel.deleted_at.is_(None),
                    )
                    .order_by(TrainingModel.gpu_index, TrainingModel.queue_order)
                )
            )
            for item in items:
                db.expunge(item)
            return items

    def model_runs(self, model_id: str) -> list[TrainingRun]:
        with self._session_factory() as db:
            items = list(
                db.scalars(
                    select(TrainingRun)
                    .where(TrainingRun.training_model_id == model_id)
                    .order_by(TrainingRun.attempt_no.desc())
                )
            )
            for item in items:
                db.expunge(item)
            return items

    def task_preparation(self, task_id: str) -> TrainingPreparation | None:
        with self._session_factory() as db:
            item = db.scalar(
                select(TrainingPreparation).where(
                    TrainingPreparation.training_task_id == task_id
                )
            )
            if item:
                db.expunge(item)
            return item

    def code_available(self, code: str) -> bool:
        clean = validate_task_code(code)
        with self._session_factory() as db:
            return db.scalar(select(TrainingTask.id).where(TrainingTask.code == clean)) is None

    def metrics(self, run_id: str, after_epoch: int = 0) -> list[TrainingMetric]:
        with self._session_factory() as db:
            items = list(
                db.scalars(
                    select(TrainingMetric)
                    .where(
                        TrainingMetric.training_run_id == run_id, TrainingMetric.epoch > after_epoch
                    )
                    .order_by(TrainingMetric.epoch)
                )
            )
            for item in items:
                db.expunge(item)
            return items

    def idempotent_result(
        self, actor: User, action: str, key: str | None
    ) -> tuple[str, str] | None:
        if not key:
            return None
        if len(key) > 128:
            raise InvalidTraining("Idempotency-Key is too long")
        with self._session_factory() as db:
            item = db.scalar(
                select(TrainingActionRequest).where(
                    TrainingActionRequest.actor_id == actor.id,
                    TrainingActionRequest.action == action,
                    TrainingActionRequest.idempotency_key == key,
                )
            )
            return (item.result_type, item.result_id) if item else None

    def remember_idempotent_result(
        self,
        actor: User,
        action: str,
        key: str | None,
        result_type: str,
        result_id: str,
    ) -> None:
        if not key:
            return
        with self._session_factory() as db:
            try:
                db.add(
                    TrainingActionRequest(
                        id=str(uuid4()),
                        actor_id=actor.id,
                        action=action,
                        idempotency_key=key,
                        result_type=result_type,
                        result_id=result_id,
                        created_at=_now(),
                    )
                )
                db.commit()
            except IntegrityError:
                db.rollback()

    def create_draft(
        self,
        actor: User,
        *,
        code: str,
        name: str,
        description: str = "",
        mode: str = "single_model",
        default_dataset_export_id: str | None = None,
        default_dataset_mode: str = "single",
        default_multi_dataset_config: object | None = None,
        default_template_id: str | None = None,
        default_base_model_id: str | None = None,
        models: list[dict[str, object]],
    ) -> TrainingTask:
        if not 1 <= len(models) <= 10:
            raise InvalidTraining("a task requires 1-10 training models")
        if mode == "single_model" and len(models) != 1:
            raise InvalidTraining("single_model requires exactly one model")
        if mode == "single_device_serial" and len(models) < 2:
            raise InvalidTraining("single_device_serial requires at least two models")
        if mode not in {"single_model", "single_device_serial", "custom_sequence"}:
            raise InvalidTraining("invalid training mode")
        if default_dataset_mode not in {"single", "multi"}:
            raise InvalidTraining("invalid task dataset mode")
        default_multi_json = _config_json(default_multi_dataset_config)
        if default_dataset_mode == "multi" and default_multi_json is None:
            raise InvalidTraining("task multi-dataset config is required")
        now = _now()
        task = TrainingTask(
            id=str(uuid4()),
            code=validate_task_code(code),
            name=_clean(name, 128, True),
            description=_clean(description, 2000),
            status="draft",
            mode=mode,
            default_dataset_export_id=default_dataset_export_id,
            default_dataset_mode=default_dataset_mode,
            default_multi_dataset_config=default_multi_json,
            default_template_id=default_template_id,
            default_base_model_id=default_base_model_id,
            created_by_id=actor.id,
            created_at=now,
            updated_at=now,
        )
        rows: list[TrainingModel] = []
        seen: set[tuple[int, int]] = set()
        for index, source in enumerate(models, 1):
            gpu, order = int(source.get("gpu_index", 0)), int(source.get("queue_order", index))
            if gpu < 0 or not 1 <= order <= 10 or (gpu, order) in seen:
                raise InvalidTraining("GPU lane order must be unique")
            seen.add((gpu, order))
            dataset_mode = _dataset_mode(
                source.get("dataset_mode"), source.get("dataset_export_id")
            )
            multi_json = _config_json(source.get("multi_dataset_config"))
            if dataset_mode == "multi" and multi_json is None:
                raise InvalidTraining(f"models[{index - 1}].multi-dataset config is required")
            rows.append(
                TrainingModel(
                    id=str(uuid4()),
                    training_task_id=task.id,
                    name=_clean(str(source.get("name") or f"模型 {index}"), 128, True),
                    description=_clean(str(source.get("description") or ""), 2000),
                    dataset_export_id=source.get("dataset_export_id") or None,
                    dataset_mode=dataset_mode,
                    multi_dataset_config=multi_json,
                    template_id=source.get("template_id") or None,
                    base_model_id=source.get("base_model_id") or None,
                    epochs_override=source.get("epochs_override") or None,
                    batch_mode_override=source.get("batch_mode_override") or None,
                    batch_value_override=source.get("batch_value_override"),
                    image_size_override=source.get("image_size_override") or None,
                    gpu_index=gpu,
                    queue_order=order,
                    status="draft",
                    created_at=now,
                    updated_at=now,
                )
            )
        if mode == "single_device_serial" and len({row.gpu_index for row in rows}) != 1:
            raise InvalidTraining("single_device_serial must use one GPU")
        with self._session_factory() as db:
            try:
                if task.default_multi_dataset_config:
                    self._multi_dataset_snapshot(db, task.default_multi_dataset_config)
                for row in rows:
                    if row.multi_dataset_config:
                        self._multi_dataset_snapshot(db, row.multi_dataset_config)
                db.add(task)
                db.flush()
                db.add_all(rows)
                db.commit()
            except IntegrityError as exc:
                db.rollback()
                raise TrainingConflict("training task code or lane already exists") from exc
            db.expunge(task)
            return task

    def update_draft(
        self, actor: User, task_id: str, *, version: int, **values: object
    ) -> TrainingTask:
        old = self.get_task(actor, task_id)
        if not self.can_manage(actor, old):
            raise TrainingForbidden("training task is read-only")
        if old.status != "draft":
            raise TrainingConflict("started training task is immutable")
        models = values.pop("models", None)
        if models is None:
            raise InvalidTraining("models are required")
        mode = str(values.get("mode") or old.mode)
        model_values = list(models)  # type: ignore[arg-type]
        if not 1 <= len(model_values) <= 10:
            raise InvalidTraining("a task requires 1-10 training models")
        if mode == "single_model" and len(model_values) != 1:
            raise InvalidTraining("single_model requires exactly one model")
        if mode == "single_device_serial" and len(model_values) < 2:
            raise InvalidTraining("single_device_serial requires at least two models")
        now = _now()
        with self._session_factory() as db:
            task = db.get(TrainingTask, task_id)
            if task is None or task.version != version:
                raise TrainingConflict("training task version conflict")
            for row in db.scalars(
                select(TrainingModel).where(TrainingModel.training_task_id == task_id)
            ):
                db.delete(row)
            db.flush()
            task.name = _clean(str(values.get("name") or ""), 128, True)
            task.description = _clean(str(values.get("description") or ""), 2000)
            task.mode = mode
            task.default_dataset_export_id = values.get("default_dataset_export_id") or None
            default_dataset_mode = str(values.get("default_dataset_mode") or "single")
            if default_dataset_mode not in {"single", "multi"}:
                raise InvalidTraining("invalid task dataset mode")
            default_multi_json = _config_json(values.get("default_multi_dataset_config"))
            if default_dataset_mode == "multi" and default_multi_json is None:
                raise InvalidTraining("task multi-dataset config is required")
            task.default_dataset_mode = default_dataset_mode
            task.default_multi_dataset_config = default_multi_json
            task.default_template_id = values.get("default_template_id") or None
            task.default_base_model_id = values.get("default_base_model_id") or None
            task.version += 1
            task.updated_at = now
            seen: set[tuple[int, int]] = set()
            for index, source in enumerate(model_values, 1):
                gpu = int(source.get("gpu_index", 0))
                order = int(source.get("queue_order", index))
                if gpu < 0 or not 1 <= order <= 10 or (gpu, order) in seen:
                    raise InvalidTraining("GPU lane order must be unique")
                seen.add((gpu, order))
                dataset_mode = _dataset_mode(
                    source.get("dataset_mode"), source.get("dataset_export_id")
                )
                multi_json = _config_json(source.get("multi_dataset_config"))
                if dataset_mode == "multi" and multi_json is None:
                    raise InvalidTraining(
                        f"models[{index - 1}].multi-dataset config is required"
                    )
                db.add(
                    TrainingModel(
                        id=str(uuid4()),
                        training_task_id=task.id,
                        name=_clean(str(source.get("name") or f"模型 {index}"), 128, True),
                        description=_clean(str(source.get("description") or ""), 2000),
                        dataset_export_id=source.get("dataset_export_id") or None,
                        dataset_mode=dataset_mode,
                        multi_dataset_config=multi_json,
                        template_id=source.get("template_id") or None,
                        base_model_id=source.get("base_model_id") or None,
                        epochs_override=source.get("epochs_override") or None,
                        batch_mode_override=source.get("batch_mode_override") or None,
                        batch_value_override=source.get("batch_value_override"),
                        image_size_override=source.get("image_size_override") or None,
                        gpu_index=gpu,
                        queue_order=order,
                        status="draft",
                        created_at=now,
                        updated_at=now,
                    )
                )
            if (
                mode == "single_device_serial"
                and len({int(row.get("gpu_index", 0)) for row in model_values}) != 1
            ):
                raise InvalidTraining("single_device_serial must use one GPU")
            if task.default_multi_dataset_config:
                self._multi_dataset_snapshot(db, task.default_multi_dataset_config)
            for row in db.scalars(
                select(TrainingModel).where(TrainingModel.training_task_id == task.id)
            ):
                if row.multi_dataset_config:
                    self._multi_dataset_snapshot(db, row.multi_dataset_config)
            db.commit()
            db.expunge(task)
            return task

    def _multi_dataset_snapshot(self, db, config_json: str | None) -> dict[str, object]:
        if not config_json:
            raise InvalidTraining("multi-dataset config is required")
        try:
            config = normalize_multi_dataset_config(json.loads(config_json))
        except (ValueError, json.JSONDecodeError) as exc:
            raise InvalidTraining(str(exc)) from exc
        export_ids = list(config["dataset_export_ids"])
        target_classes = list(config["target_classes"])
        targets = {name: index for index, name in enumerate(target_classes)}
        exports = {
            item.id: item
            for item in db.scalars(select(DatasetExport).where(DatasetExport.id.in_(export_ids)))
        }
        sources: list[dict[str, object]] = []
        available: set[str] = set()
        for export_id in export_ids:
            dataset = exports.get(export_id)
            if (
                dataset is None
                or dataset.deleted_at is not None
                or dataset.status != "ready"
                or not dataset.storage_path
            ):
                raise InvalidTraining(f"dataset export is not ready: {export_id}")
            try:
                manifest = json.loads(dataset.manifest or "{}")
                classes = source_classes(manifest)
            except (ValueError, json.JSONDecodeError) as exc:
                raise InvalidTraining(f"dataset export manifest is invalid: {export_id}") from exc
            project = db.get(Project, dataset.project_id)
            available.update(name for _index, name in classes)
            sources.append(
                {
                    "dataset_export_id": dataset.id,
                    "dataset_name": dataset.name,
                    "project_id": dataset.project_id,
                    "project_name": project.name if project else "",
                    "storage_path": dataset.storage_path,
                    "manifest": manifest,
                    "class_map": {
                        str(source_index): targets[name]
                        for source_index, name in classes
                        if name in targets
                    },
                }
            )
        missing = [name for name in target_classes if name not in available]
        if missing:
            raise InvalidTraining(f"target classes are unavailable: {', '.join(missing)}")
        hash_input = {
            "version": 1,
            "dataset_export_ids": export_ids,
            "target_classes": target_classes,
            "sources": [
                {
                    "dataset_export_id": source["dataset_export_id"],
                    "manifest": source["manifest"],
                    "class_map": source["class_map"],
                }
                for source in sources
            ],
        }
        return {
            "version": 1,
            "kind": "multi",
            "config_hash": snapshot_hash(hash_input),
            "target_classes": target_classes,
            "sources": sources,
        }

    def _effective_dataset_snapshot(
        self, db, task: TrainingTask, model: TrainingModel, index: int
    ) -> dict[str, object]:
        mode = model.dataset_mode
        config_json = model.multi_dataset_config
        dataset_id = model.dataset_export_id
        if mode == "inherit":
            mode = task.default_dataset_mode
            config_json = task.default_multi_dataset_config
            dataset_id = task.default_dataset_export_id
        if mode == "multi":
            return self._multi_dataset_snapshot(db, config_json)
        dataset = db.get(DatasetExport, dataset_id) if dataset_id else None
        if (
            dataset is None
            or dataset.deleted_at is not None
            or dataset.status != "ready"
            or not dataset.storage_path
        ):
            raise InvalidTraining(f"models[{index}].dataset is not ready")
        return {
            "version": 1,
            "kind": "single",
            "id": dataset.id,
            "name": dataset.name,
            "storage_path": dataset.storage_path,
            "manifest": json.loads(dataset.manifest or "{}"),
        }

    def start(
        self, actor: User, task_id: str, *, available_gpu_indices: set[int] | None = None
    ) -> TrainingTask:
        task_check = self.get_task(actor, task_id)
        if not self.can_manage(actor, task_check):
            raise TrainingForbidden("training task is read-only")
        if task_check.status != "draft":
            raise TrainingConflict("training task has already started")
        now = _now()
        with self._session_factory() as db:
            task = db.get(TrainingTask, task_id)
            assert task is not None
            models = list(
                db.scalars(
                    select(TrainingModel)
                    .where(
                        TrainingModel.training_task_id == task_id,
                        TrainingModel.deleted_at.is_(None),
                    )
                    .order_by(TrainingModel.gpu_index, TrainingModel.queue_order)
                )
            )
            issues: list[str] = []
            for index, row in enumerate(models):
                issue_count = len(issues)
                template_id = row.template_id or task.default_template_id
                base_id = row.base_model_id or task.default_base_model_id
                template = db.get(HyperparameterTemplate, template_id) if template_id else None
                base = db.get(InferenceModel, base_id) if base_id else None
                try:
                    dataset_snapshot = self._effective_dataset_snapshot(db, task, row, index)
                except InvalidTraining as exc:
                    issues.append(str(exc))
                    dataset_snapshot = None
                if template is None or template.deleted_at is not None:
                    issues.append(f"models[{index}].template is unavailable")
                if (
                    base is None
                    or base.deleted_at is not None
                    or base.status != "ready"
                    or not base.storage_path
                ):
                    issues.append(f"models[{index}].base_model is not ready")
                if available_gpu_indices is not None and row.gpu_index not in available_gpu_indices:
                    issues.append(f"models[{index}].gpu is unavailable")
                if len(issues) > issue_count:
                    continue
                assert dataset_snapshot and template and base
                parameters = effective_parameters(
                    template.epochs,
                    template.batch_mode,
                    template.batch_value,
                    template.image_size,
                    json.loads(template.extra_parameters),
                )
                if row.epochs_override is not None:
                    parameters["epochs"] = row.epochs_override
                if row.batch_mode_override is not None:
                    parameters["batch"] = (
                        -1 if row.batch_mode_override == "auto" else row.batch_value_override
                    )
                if row.image_size_override is not None:
                    parameters["imgsz"] = row.image_size_override
                try:
                    normalized = validate_values(parameters)
                except HyperparameterValidationError as exc:
                    issues.extend(
                        f"models[{index}].hyperparameters.{issue.key or 'value'}: {issue.message}"
                        for issue in exc.issues
                    )
                    continue
                parameters = effective_parameters(
                    normalized["epochs"],
                    normalized["batch_mode"],
                    normalized["batch_value"],
                    normalized["image_size"],
                    normalized["extra_parameters"],
                )
                row.template_id, row.base_model_id = template.id, base.id
                row.dataset_snapshot = json.dumps(dataset_snapshot, ensure_ascii=False)
                row.template_snapshot = json.dumps(
                    {"id": template.id, "name": template.name, "parameters": parameters},
                    ensure_ascii=False,
                )
                row.base_model_snapshot = json.dumps(
                    {
                        "id": base.id,
                        "name": base.name,
                        "model_code": base.model_code,
                        "storage_path": base.storage_path,
                        "sha256": base.sha256,
                    },
                    ensure_ascii=False,
                )
                row.artifact_code = build_artifact_code(
                    task_code=task.code,
                    training_date=now.date(),
                    gpu_index=row.gpu_index,
                    queue_order=row.queue_order,
                    base_code=base.model_code,
                    image_size=int(parameters["imgsz"]),
                    batch_mode=normalized["batch_mode"],
                    batch_value=normalized["batch_value"],
                    epochs=int(parameters["epochs"]),
                )
                row.status = "queued"
                row.updated_at = now
            if issues:
                raise InvalidTraining("; ".join(issues))
            needs_preparation = any(
                json.loads(row.dataset_snapshot).get("kind") == "multi" for row in models
            )
            if needs_preparation:
                preparation_id = str(uuid4())
                db.add(
                    TrainingPreparation(
                        id=preparation_id,
                        training_task_id=task.id,
                        status="queued",
                        phase="waiting",
                        run_token=secrets.token_hex(24),
                        storage_path=f"training/tasks/{task.id}/preparation",
                        created_at=now,
                    )
                )
                for row in models:
                    row.status = "preparing"
                task.status = "preparing"
            else:
                self._queue_initial_runs(db, task, models, now)
            task.submitted_at = task.last_run_at = now
            task.updated_at = now
            task.version += 1
            db.commit()
            db.expunge(task)
            return task

    @staticmethod
    def _queue_initial_runs(db, task: TrainingTask, models: list[TrainingModel], now) -> None:
        for row in models:
            run_id = str(uuid4())
            db.add(
                TrainingRun(
                    id=run_id,
                    training_model_id=row.id,
                    attempt_no=1,
                    kind="initial",
                    status="queued",
                    gpu_index=row.gpu_index,
                    queue_order=row.queue_order,
                    run_token=secrets.token_hex(24),
                    target_epochs=json.loads(row.template_snapshot)["parameters"]["epochs"],
                    storage_path=f"training/tasks/{task.id}/models/{row.id}/runs/{run_id}",
                    enqueued_at=now,
                )
            )
            row.status = "queued"
            row.updated_at = now
        task.status = "queued"

    def cancel(self, actor: User, task_id: str) -> TrainingTask:
        check = self.get_task(actor, task_id)
        if not self.can_manage(actor, check):
            raise TrainingForbidden("training task is read-only")
        with self._session_factory() as db:
            task = db.get(TrainingTask, task_id)
            assert task
            if task.status not in ACTIVE:
                raise TrainingConflict("training task is not active")
            preparation = db.scalar(
                select(TrainingPreparation).where(
                    TrainingPreparation.training_task_id == task_id,
                    TrainingPreparation.status.in_(("queued", "running", "canceling")),
                )
            )
            if preparation:
                now = _now()
                preparation.status = (
                    "canceled" if preparation.status == "queued" else "canceling"
                )
                if preparation.status == "canceled":
                    preparation.finished_at = now
                for model in db.scalars(
                    select(TrainingModel).where(TrainingModel.training_task_id == task_id)
                ):
                    model.status = (
                        "canceled" if preparation.status == "canceled" else "canceling"
                    )
                    model.finished_at = now if preparation.status == "canceled" else None
                task.status = "canceled" if preparation.status == "canceled" else "canceling"
                task.finished_at = now if preparation.status == "canceled" else None
                db.commit()
                db.expunge(task)
                return task
            models = list(
                db.scalars(
                    select(TrainingModel).where(
                        TrainingModel.training_task_id == task_id, TrainingModel.status.in_(ACTIVE)
                    )
                )
            )
            for model in models:
                run = db.scalar(
                    select(TrainingRun)
                    .where(
                        TrainingRun.training_model_id == model.id, TrainingRun.status.in_(ACTIVE)
                    )
                    .order_by(TrainingRun.attempt_no.desc())
                )
                if run and run.status == "queued":
                    run.status = model.status = "canceled"
                    run.finished_at = model.finished_at = _now()
                elif run:
                    run.status = model.status = "canceling"
            task.status = (
                "canceling" if any(row.status == "canceling" for row in models) else "canceled"
            )
            if task.status == "canceled":
                task.finished_at = _now()
            db.commit()
            db.expunge(task)
            return task

    def retry_preparation(self, actor: User, task_id: str) -> TrainingTask:
        task_check = self.get_task(actor, task_id)
        if not self.can_manage(actor, task_check):
            raise TrainingForbidden("training task is read-only")
        with self._session_factory() as db:
            task = db.get(TrainingTask, task_id)
            preparation = db.scalar(
                select(TrainingPreparation).where(
                    TrainingPreparation.training_task_id == task_id
                )
            )
            if task is None or preparation is None:
                raise TrainingNotFound("training preparation not found")
            if task.status != "preparation_failed" or preparation.status != "failed":
                raise TrainingConflict("training preparation is not retryable")
            now = _now()
            preparation.status = "queued"
            preparation.phase = "waiting"
            preparation.progress = 0
            preparation.processed = 0
            preparation.total = 0
            preparation.pid = None
            preparation.run_token = secrets.token_hex(24)
            preparation.worker_id = None
            preparation.lease_expires_at = None
            preparation.event_offset = 0
            preparation.last_sequence = 0
            preparation.error = None
            preparation.started_at = None
            preparation.finished_at = None
            for model in db.scalars(
                select(TrainingModel).where(TrainingModel.training_task_id == task_id)
            ):
                model.status = "preparing"
                model.finished_at = None
            task.status = "preparing"
            task.finished_at = None
            task.updated_at = now
            db.commit()
            db.expunge(task)
            return task

    def cancel_model(self, actor: User, model_id: str) -> None:
        with self._session_factory() as db:
            model = db.get(TrainingModel, model_id)
            if model is None or model.deleted_at is not None:
                raise TrainingNotFound("training model not found")
            task = db.get(TrainingTask, model.training_task_id)
            assert task
            if not self.can_manage(actor, task):
                raise TrainingForbidden("training model is read-only")
            if model.status not in ACTIVE:
                raise TrainingConflict("training model is not active")
            run = db.scalar(
                select(TrainingRun)
                .where(TrainingRun.training_model_id == model.id, TrainingRun.status.in_(ACTIVE))
                .order_by(TrainingRun.attempt_no.desc())
            )
            if run and run.status == "queued":
                run.status = model.status = "canceled"
                run.finished_at = model.finished_at = _now()
            elif run:
                run.status = model.status = "canceling"
            db.commit()

    def new_run(
        self, actor: User, model_id: str, kind: str, *, confirm_replace: bool = False
    ) -> TrainingRun:
        with self._session_factory() as db:
            model = db.get(TrainingModel, model_id)
            if model is None or model.deleted_at is not None:
                raise TrainingNotFound("training model not found")
            task = db.get(TrainingTask, model.training_task_id)
            assert task
            if not self.can_manage(actor, task):
                raise TrainingForbidden("training model is read-only")
            latest = db.scalar(
                select(TrainingRun)
                .where(TrainingRun.training_model_id == model.id)
                .order_by(TrainingRun.attempt_no.desc())
            )
            if latest is None or model.status in ACTIVE:
                raise TrainingConflict("training model is active")
            if kind == "retry" and model.status == "succeeded" and not confirm_replace:
                raise TrainingConflict("confirm_replace is required for a succeeded model")
            if kind == "resume" and (
                not latest.last_path
                or latest.current_epoch < 1
                or model.status not in {"failed", "canceled"}
            ):
                raise TrainingConflict("last.pt is unavailable for resume")
            now, run_id = _now(), str(uuid4())
            run = TrainingRun(
                id=run_id,
                training_model_id=model.id,
                attempt_no=latest.attempt_no + 1,
                kind=kind,
                status="queued",
                gpu_index=model.gpu_index,
                queue_order=model.queue_order,
                run_token=secrets.token_hex(24),
                target_epochs=latest.target_epochs,
                storage_path=f"training/tasks/{task.id}/models/{model.id}/runs/{run_id}",
                enqueued_at=now,
            )
            db.add(run)
            model.status = "queued"
            model.progress = 0
            model.finished_at = None
            task.status = "queued"
            task.finished_at = None
            task.last_run_at = now
            db.commit()
            db.expunge(run)
            return run

    def derive_model(
        self,
        actor: User,
        model_id: str,
        *,
        task_code: str,
        task_name: str,
        description: str = "",
        epochs: int | None = None,
        batch_mode: str | None = None,
        batch_value: float | None = None,
        image_size: int | None = None,
        gpu_index: int = 0,
    ) -> TrainingTask:
        with self._session_factory() as db:
            source = db.get(TrainingModel, model_id)
            if source is None:
                raise TrainingNotFound("training model not found")
            old_task = db.get(TrainingTask, source.training_task_id)
            assert old_task
            if not self.can_manage(actor, old_task) or source.status in ACTIVE:
                raise TrainingForbidden("training model cannot be derived")
            values = {
                "name": source.name,
                "description": source.description,
                "dataset_export_id": source.dataset_export_id,
                "template_id": source.template_id,
                "base_model_id": source.base_model_id,
                "epochs_override": epochs if epochs is not None else source.epochs_override,
                "batch_mode_override": batch_mode
                if batch_mode is not None
                else source.batch_mode_override,
                "batch_value_override": batch_value
                if batch_mode is not None
                else source.batch_value_override,
                "image_size_override": image_size
                if image_size is not None
                else source.image_size_override,
                "gpu_index": gpu_index,
                "queue_order": 1,
            }
        task = self.create_draft(
            actor,
            code=task_code,
            name=task_name,
            description=description,
            mode="single_model",
            models=[values],
        )
        with self._session_factory() as db:
            row = db.scalar(select(TrainingModel).where(TrainingModel.training_task_id == task.id))
            row.derived_from_id = model_id
            db.commit()
        return task

    def retry_failed(self, actor: User, task_id: str) -> TrainingTask:
        task = self.get_task(actor, task_id)
        if not self.can_manage(actor, task):
            raise TrainingForbidden("training task is read-only")
        if task.status in ACTIVE or task.status == "draft":
            raise TrainingConflict("training task is active")
        candidates = [
            row
            for row in self.task_models(task_id)
            if row.status in {"failed", "canceled", "start_failed"}
        ]
        if not candidates:
            raise TrainingConflict("training task has no failed models")
        for row in candidates:
            self.new_run(actor, row.id, "retry")
        return self.get_task(actor, task_id)

    def resume_interrupted(self, actor: User, task_id: str) -> TrainingTask:
        task = self.get_task(actor, task_id)
        if not self.can_manage(actor, task) or task.status in ACTIVE or task.status == "draft":
            raise TrainingConflict("training task cannot be resumed")
        resumed = 0
        for model in self.task_models(task_id):
            latest = self.model_runs(model.id)
            run = latest[0] if latest else None
            if (
                model.status in {"failed", "canceled"}
                and run
                and run.last_path
                and run.current_epoch > 0
                and (self.workspace / run.last_path).is_file()
            ):
                self.new_run(actor, model.id, "resume")
                resumed += 1
        if not resumed:
            raise TrainingConflict("no interrupted model has an available last.pt")
        return self.get_task(actor, task_id)

    def derive_task(
        self,
        actor: User,
        task_id: str,
        *,
        task_code: str,
        task_name: str,
        description: str = "",
    ) -> TrainingTask:
        source_task = self.get_task(actor, task_id)
        if not self.can_manage(actor, source_task):
            raise TrainingForbidden("training task is read-only")
        if source_task.status in ACTIVE:
            raise TrainingConflict("active training task cannot be derived")
        source_models = self.task_models(task_id)
        rows = [
            {
                "name": row.name,
                "description": row.description,
                "dataset_export_id": row.dataset_export_id,
                "template_id": row.template_id,
                "base_model_id": row.base_model_id,
                "epochs_override": row.epochs_override,
                "batch_mode_override": row.batch_mode_override,
                "batch_value_override": row.batch_value_override,
                "image_size_override": row.image_size_override,
                "gpu_index": row.gpu_index,
                "queue_order": row.queue_order,
            }
            for row in source_models
        ]
        created = self.create_draft(
            actor,
            code=task_code,
            name=task_name,
            description=description,
            mode=source_task.mode,
            models=rows,
        )
        with self._session_factory() as db:
            created_rows = list(
                db.scalars(
                    select(TrainingModel)
                    .where(TrainingModel.training_task_id == created.id)
                    .order_by(TrainingModel.gpu_index, TrainingModel.queue_order)
                )
            )
            for target, source in zip(created_rows, source_models, strict=True):
                target.derived_from_id = source.id
            db.commit()
        return created

    def extend_model(
        self,
        actor: User,
        model_id: str,
        *,
        task_code: str,
        task_name: str,
        additional_epochs: int,
        checkpoint: str = "best",
        gpu_index: int = 0,
    ) -> TrainingTask:
        if additional_epochs < 1:
            raise InvalidTraining("additional_epochs must be positive")
        if checkpoint not in {"best", "last"}:
            raise InvalidTraining("checkpoint must be best or last")
        with self._session_factory() as db:
            source = db.get(TrainingModel, model_id)
            if source is None or source.deleted_at is not None:
                raise TrainingNotFound("training model not found")
            source_task = db.get(TrainingTask, source.training_task_id)
            assert source_task is not None
            if not self.can_manage(actor, source_task):
                raise TrainingForbidden("training model is read-only")
            latest = db.scalar(
                select(TrainingRun)
                .where(TrainingRun.training_model_id == model_id)
                .order_by(TrainingRun.attempt_no.desc())
            )
            path = (
                latest.best_path
                if latest and checkpoint == "best"
                else latest.last_path
                if latest
                else None
            )
            if source.status != "succeeded" or not path or not (self.workspace / path).is_file():
                raise TrainingConflict("checkpoint is unavailable for additional training")
        task = self.derive_model(
            actor,
            model_id,
            task_code=task_code,
            task_name=task_name,
            epochs=additional_epochs,
            gpu_index=gpu_index,
        )
        with self._session_factory() as db:
            row = db.scalar(select(TrainingModel).where(TrainingModel.training_task_id == task.id))
            assert row
            row.derived_from_id = None
            row.continuation_of_id = model_id
            row.continuation_checkpoint = checkpoint
            db.commit()
        return task

    def delete_task(self, actor: User, task_id: str) -> None:
        task = self.get_task(actor, task_id)
        if not self.can_manage(actor, task):
            raise TrainingForbidden("training task is read-only")
        if task.status in ACTIVE:
            raise TrainingConflict("active training task cannot be deleted")
        source = self.workspace / "training" / "tasks" / task_id
        target = self.workspace / ".deleted" / "training-tasks" / task_id
        if source.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))
        with self._session_factory() as db:
            item = db.get(TrainingTask, task_id)
            item.deleted_at = _now()
            db.commit()

    def delete_model(
        self, actor: User, model_id: str, *, confirm_published_model: bool = False
    ) -> None:
        with self._session_factory() as db:
            model = db.get(TrainingModel, model_id)
            if model is None or model.deleted_at is not None:
                raise TrainingNotFound("training model not found")
            task = db.get(TrainingTask, model.training_task_id)
            assert task is not None
            if not self.can_manage(actor, task):
                raise TrainingForbidden("training model is read-only")
            if model.status in ACTIVE:
                raise TrainingConflict("active training model cannot be deleted")
            published = db.scalar(
                select(InferenceModel).where(InferenceModel.training_model_id == model.id)
            )
            if published is not None and published.deleted_at is None:
                if not confirm_published_model:
                    raise TrainingConflict("confirm_published_model is required")
                published.deleted_at = _now()
                published.version += 1
                published_dir = self.workspace / "models" / published.id
                published_archive = (
                    self.workspace / ".deleted" / "training-models" / model.id / "published"
                )
                if published_dir.exists():
                    published_archive.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(published_dir), str(published_archive))
            source = self.workspace / "training" / "tasks" / task.id / "models" / model.id
            archive = self.workspace / ".deleted" / "training-models" / model.id / "runs"
            if source.exists():
                archive.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(source), str(archive))
            model.deleted_at = _now()
            db.commit()

    def action_availability(
        self, model: TrainingModel, run: TrainingRun | None
    ) -> dict[str, object]:
        has_last = bool(run and run.last_path and (self.workspace / run.last_path).is_file())
        has_best = bool(run and run.best_path and (self.workspace / run.best_path).is_file())
        return {
            key: value.__dict__
            for key, value in model_actions(
                model.status, has_last=has_last, has_best=has_best
            ).items()
        }

    def task_action_availability(
        self, task: TrainingTask, models: list[TrainingModel]
    ) -> dict[str, object]:
        has_resumable = False
        for model in models:
            runs = self.model_runs(model.id)
            latest = runs[0] if runs else None
            if (
                model.status in {"failed", "canceled"}
                and latest
                and latest.last_path
                and latest.current_epoch > 0
                and (self.workspace / latest.last_path).is_file()
            ):
                has_resumable = True
                break
        return {
            key: value.__dict__
            for key, value in task_actions(
                task.status, [model.status for model in models], has_resumable=has_resumable
            ).items()
        }
