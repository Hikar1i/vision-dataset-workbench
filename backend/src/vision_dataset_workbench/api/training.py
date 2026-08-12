import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from ..models import (
    DatasetExport,
    HyperparameterTemplate,
    InferenceModel,
    ModelProject,
    Project,
    TrainingModel,
    TrainingPreparation,
    TrainingRun,
    TrainingTask,
    User,
)
from ..services.training import (
    InvalidTraining,
    TrainingConflict,
    TrainingForbidden,
    TrainingNotFound,
    TrainingService,
)
from ..training.telemetry import training_telemetry
from ..training.events import terminal_snapshot
from .auth import current_user, require_same_origin

router = APIRouter(prefix="/api/v1", tags=["training"])


class MultiDatasetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal[1] = 1
    dataset_export_ids: list[str] = Field(min_length=1)
    target_classes: list[str] = Field(min_length=1)


class TrainingModelInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    dataset_export_id: str | None = None
    dataset_mode: Literal["inherit", "single", "multi"] | None = None
    multi_dataset_config: MultiDatasetConfig | None = None
    template_id: str | None = None
    base_model_id: str | None = None
    epochs_override: int | None = None
    batch_mode_override: Literal["auto", "fixed", "fraction"] | None = None
    batch_value_override: float | None = None
    image_size_override: int | None = None
    gpu_index: int = Field(default=0, ge=0)
    queue_order: int = Field(default=1, ge=1, le=10)


class CreateTrainingTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    mode: Literal["single_model", "single_device_serial", "custom_sequence"] = "single_model"
    default_dataset_export_id: str | None = None
    default_dataset_mode: Literal["single", "multi"] = "single"
    default_multi_dataset_config: MultiDatasetConfig | None = None
    default_template_id: str | None = None
    default_base_model_id: str | None = None
    models: list[TrainingModelInput] = Field(min_length=1, max_length=10)


class UpdateTrainingTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    mode: Literal["single_model", "single_device_serial", "custom_sequence"]
    default_dataset_export_id: str | None = None
    default_dataset_mode: Literal["single", "multi"] = "single"
    default_multi_dataset_config: MultiDatasetConfig | None = None
    default_template_id: str | None = None
    default_base_model_id: str | None = None
    models: list[TrainingModelInput] = Field(min_length=1, max_length=10)


class ConfirmRetryRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    confirm_replace: bool = False


class DeriveModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_code: str
    task_name: str
    description: str = ""
    epochs: int | None = None
    batch_mode: Literal["auto", "fixed", "fraction"] | None = None
    batch_value: float | None = None
    image_size: int | None = None
    gpu_index: int = Field(default=0, ge=0)


class ExtendModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_code: str
    task_name: str
    additional_epochs: int = Field(ge=1)
    checkpoint: Literal["best", "last"] = "best"
    gpu_index: int = Field(default=0, ge=0)


class DeriveTaskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    task_code: str
    task_name: str
    description: str = ""


def service(request: Request) -> TrainingService:
    value = request.app.state.training_service
    if value is None:
        raise HTTPException(503, "workspace is not initialized")
    return value


def _raise(exc: ValueError) -> NoReturn:
    if isinstance(exc, TrainingNotFound):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, TrainingForbidden):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, TrainingConflict):
        raise HTTPException(409, str(exc)) from exc
    raise HTTPException(422, str(exc)) from exc


def _time(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def run_response(run: TrainingRun) -> dict[str, object]:
    return {
        "id": run.id,
        "attempt_no": run.attempt_no,
        "kind": run.kind,
        "status": run.status,
        "gpu_index": run.gpu_index,
        "pid": run.pid,
        "current_epoch": run.current_epoch,
        "target_epochs": run.target_epochs,
        "progress": run.progress,
        "best_path": run.best_path,
        "last_path": run.last_path,
        "host_snapshot": json.loads(run.host_snapshot),
        "error": run.error,
        "warning": run.warning,
        "enqueued_at": _time(run.enqueued_at),
        "started_at": _time(run.started_at),
        "finished_at": _time(run.finished_at),
    }


def model_response(svc: TrainingService, model: TrainingModel) -> dict[str, object]:
    runs = svc.model_runs(model.id)
    latest = runs[0] if runs else None
    return {
        "id": model.id,
        "training_task_id": model.training_task_id,
        "name": model.name,
        "description": model.description,
        "artifact_code": model.artifact_code,
        "dataset_export_id": model.dataset_export_id,
        "dataset_mode": model.dataset_mode,
        "multi_dataset_config": (
            json.loads(model.multi_dataset_config) if model.multi_dataset_config else None
        ),
        "template_id": model.template_id,
        "base_model_id": model.base_model_id,
        "epochs_override": model.epochs_override,
        "batch_mode_override": model.batch_mode_override,
        "batch_value_override": model.batch_value_override,
        "image_size_override": model.image_size_override,
        "gpu_index": model.gpu_index,
        "queue_order": model.queue_order,
        "status": model.status,
        "progress": model.progress,
        "derived_from_id": model.derived_from_id,
        "continuation_of_id": model.continuation_of_id,
        "continuation_checkpoint": model.continuation_checkpoint,
        "dataset_snapshot": json.loads(model.dataset_snapshot),
        "template_snapshot": json.loads(model.template_snapshot),
        "base_model_snapshot": json.loads(model.base_model_snapshot),
        "actions": svc.action_availability(model, latest),
        "runs": [run_response(run) for run in runs],
        "started_at": _time(model.started_at),
        "finished_at": _time(model.finished_at),
        "created_at": _time(model.created_at),
        "updated_at": _time(model.updated_at),
    }


def task_response(
    svc: TrainingService, actor: User, task: TrainingTask, details: bool = False
) -> dict[str, object]:
    models = svc.task_models(task.id)
    value = {
        "id": task.id,
        "code": task.code,
        "name": task.name,
        "description": task.description,
        "status": task.status,
        "mode": task.mode,
        "progress": task.progress,
        "model_count": len(models),
        "default_dataset_export_id": task.default_dataset_export_id,
        "default_dataset_mode": task.default_dataset_mode,
        "default_multi_dataset_config": (
            json.loads(task.default_multi_dataset_config)
            if task.default_multi_dataset_config
            else None
        ),
        "default_template_id": task.default_template_id,
        "default_base_model_id": task.default_base_model_id,
        "created_by_id": task.created_by_id,
        "can_manage": svc.can_manage(actor, task),
        "version": task.version,
        "submitted_at": _time(task.submitted_at),
        "last_run_at": _time(task.last_run_at),
        "started_at": _time(task.started_at),
        "finished_at": _time(task.finished_at),
        "created_at": _time(task.created_at),
        "updated_at": _time(task.updated_at),
        "actions": svc.task_action_availability(task, models),
    }
    if details:
        value["models"] = [model_response(svc, row) for row in models]
        preparation = svc.task_preparation(task.id)
        value["preparation"] = (
            preparation_response(preparation, models) if preparation else None
        )
    return value


def preparation_response(
    item: TrainingPreparation, models: list[TrainingModel]
) -> dict[str, object]:
    artifacts: dict[str, dict[str, object]] = {}
    for model in models:
        snapshot = json.loads(model.dataset_snapshot or "{}")
        config_hash = snapshot.get("config_hash")
        if snapshot.get("kind") != "multi" or not isinstance(config_hash, str):
            continue
        stats = snapshot.get("stats")
        if not isinstance(stats, dict):
            continue
        artifacts.setdefault(
            config_hash,
            {
                "config_hash": config_hash,
                "dataset_count": len(snapshot.get("sources") or []),
                "images": int(stats.get("images") or 0),
                "annotations": int(stats.get("annotations") or 0),
                "ignored_annotations": int(stats.get("ignored_annotations") or 0),
                "negative_images": int(stats.get("negative_images") or 0),
            },
        )
    return {
        "id": item.id,
        "status": item.status,
        "phase": item.phase,
        "progress": item.progress,
        "processed": item.processed,
        "total": item.total,
        "error": item.error,
        "started_at": _time(item.started_at),
        "finished_at": _time(item.finished_at),
        "artifacts": list(artifacts.values()),
    }


@router.get("/training/capabilities")
def capabilities(
    request: Request, user: Annotated[User, Depends(current_user)]
) -> dict[str, object]:
    telemetry = training_telemetry()
    feature = request.app.state.capabilities.features.model_training
    telemetry["training_available"] = feature.available and telemetry["available"]
    telemetry["training_reason"] = feature.reason or telemetry["reason"]
    return telemetry


@router.get("/training/resources")
def training_resources(
    request: Request, user: Annotated[User, Depends(current_user)]
) -> dict[str, object]:
    svc = service(request)
    with svc._session_factory() as db:
        datasets = db.execute(
            select(DatasetExport, Project.id, Project.name)
            .join(Project, Project.id == DatasetExport.project_id)
            .where(DatasetExport.status == "ready", DatasetExport.deleted_at.is_(None))
            .order_by(DatasetExport.created_at.desc())
        ).all()
        templates = list(
            db.scalars(
                select(HyperparameterTemplate)
                .where(HyperparameterTemplate.deleted_at.is_(None))
                .order_by(HyperparameterTemplate.created_at.desc())
            )
        )
        models = db.execute(
            select(InferenceModel, ModelProject.id, ModelProject.name)
            .join(ModelProject, ModelProject.id == InferenceModel.model_project_id)
            .where(
                InferenceModel.status == "ready",
                InferenceModel.deleted_at.is_(None),
                ModelProject.deleted_at.is_(None),
            )
            .order_by(InferenceModel.created_at.desc())
        ).all()
        return {
            "datasets": [
                {
                    "id": item.id,
                    "name": item.name,
                    "project_id": project_id,
                    "project_name": project_name,
                    "total_frames": item.total_frames,
                    "train_frames": item.train_frames,
                    "val_frames": item.val_frames,
                    "labels": [
                        {"index": index, "name": name}
                        for index, name in _resource_labels(item)
                    ],
                }
                for item, project_id, project_name in datasets
            ],
            "templates": [
                {
                    "id": item.id,
                    "name": item.name,
                    "epochs": item.epochs,
                    "batch_mode": item.batch_mode,
                    "batch_value": item.batch_value,
                    "image_size": item.image_size,
                }
                for item in templates
            ],
            "base_models": [
                {
                    "id": item.id,
                    "name": item.name,
                    "model_code": item.model_code,
                    "project_id": project_id,
                    "project_name": project_name,
                }
                for item, project_id, project_name in models
            ],
        }


def _resource_labels(item: DatasetExport) -> list[tuple[int, str]]:
    try:
        labels = json.loads(item.manifest or "{}").get("labels", [])
        return [
            (int(label.get("mapping", index)), str(label.get("name") or "").strip())
            for index, label in enumerate(labels)
            if isinstance(label, dict)
            and label.get("enabled") is not False
            and str(label.get("name") or "").strip()
        ]
    except (TypeError, ValueError, json.JSONDecodeError):
        return []


@router.get("/training-tasks")
def list_tasks(
    request: Request, user: Annotated[User, Depends(current_user)]
) -> list[dict[str, object]]:
    svc = service(request)
    return [task_response(svc, user, item) for item in svc.list_tasks(user)]


@router.get("/training-tasks/code-availability")
def task_code_availability(
    code: Annotated[str, Query(min_length=1, max_length=64)],
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, object]:
    try:
        available = service(request).code_available(code)
        return {"code": code, "available": available, "reason": None if available else "编码已存在"}
    except ValueError as exc:
        return {"code": code, "available": False, "reason": str(exc)}


@router.post("/training-tasks", status_code=status.HTTP_201_CREATED)
def create_task(
    payload: CreateTrainingTaskRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, object]:
    require_same_origin(request)
    svc = service(request)
    try:
        item = svc.create_draft(
            user,
            **payload.model_dump(exclude_none=False, exclude={"models"}),
            models=[row.model_dump() for row in payload.models],
        )
    except (InvalidTraining, TrainingConflict) as exc:
        _raise(exc)
    return task_response(svc, user, item, True)


@router.get("/training-tasks/{task_id}")
def get_task(
    task_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> dict[str, object]:
    svc = service(request)
    try:
        item = svc.get_task(user, task_id)
    except TrainingNotFound as exc:
        _raise(exc)
    return task_response(svc, user, item, True)


@router.patch("/training-tasks/{task_id}")
def update_task(
    task_id: str,
    payload: UpdateTrainingTaskRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, object]:
    require_same_origin(request)
    svc = service(request)
    try:
        item = svc.update_draft(
            user,
            task_id,
            **payload.model_dump(exclude={"models"}),
            models=[row.model_dump() for row in payload.models],
        )
    except (InvalidTraining, TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return task_response(svc, user, item, True)


@router.post("/training-tasks/{task_id}/start")
def start_task(
    task_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> dict[str, object]:
    require_same_origin(request)
    svc = service(request)
    info = training_telemetry()
    available = {int(row["index"]) for row in info["devices"]}
    if not request.app.state.capabilities.features.model_training.available:
        raise HTTPException(409, request.app.state.capabilities.features.model_training.reason)
    try:
        item = svc.start(user, task_id, available_gpu_indices=available)
    except (InvalidTraining, TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return task_response(svc, user, item, True)


@router.post("/training-tasks/{task_id}/cancel")
def cancel_task(
    task_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> dict[str, object]:
    require_same_origin(request)
    svc = service(request)
    try:
        item = svc.cancel(user, task_id)
    except (InvalidTraining, TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return task_response(svc, user, item, True)


@router.post("/training-tasks/{task_id}/retry-preparation")
def retry_preparation(
    task_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> dict[str, object]:
    require_same_origin(request)
    svc = service(request)
    try:
        item = svc.retry_preparation(user, task_id)
    except (TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return task_response(svc, user, item, True)


@router.get("/training-tasks/{task_id}/preparation-log")
def preparation_log(
    task_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    cursor: int = Query(0, ge=0),
) -> dict[str, object]:
    svc = service(request)
    try:
        svc.get_task(user, task_id)
    except TrainingNotFound as exc:
        _raise(exc)
    item = svc.task_preparation(task_id)
    if item is None:
        raise HTTPException(404, "training preparation not found")
    path = svc.workspace / item.storage_path / "prepare.log"
    if not path.is_file():
        return {"content": "", "next_cursor": cursor}
    content, next_cursor = terminal_snapshot(path)
    return {"content": content, "next_cursor": next_cursor}


@router.post("/training-tasks/{task_id}/retry-failed")
def retry_failed(
    task_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    require_same_origin(request)
    svc = service(request)
    try:
        action = f"retry-failed:{task_id}"
        previous = svc.idempotent_result(user, action, idempotency_key)
        item = svc.get_task(user, previous[1]) if previous else svc.retry_failed(user, task_id)
        svc.remember_idempotent_result(user, action, idempotency_key, "task", item.id)
    except (TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return task_response(svc, user, item, True)


@router.post("/training-tasks/{task_id}/resume-interrupted")
def resume_interrupted(
    task_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> dict[str, object]:
    require_same_origin(request)
    svc = service(request)
    try:
        item = svc.resume_interrupted(user, task_id)
    except (TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return task_response(svc, user, item, True)


@router.post("/training-tasks/{task_id}/derive", status_code=201)
def derive_task(
    task_id: str,
    payload: DeriveTaskRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    require_same_origin(request)
    svc = service(request)
    try:
        action = f"derive-task:{task_id}"
        previous = svc.idempotent_result(user, action, idempotency_key)
        item = (
            svc.get_task(user, previous[1])
            if previous
            else svc.derive_task(user, task_id, **payload.model_dump())
        )
        svc.remember_idempotent_result(user, action, idempotency_key, "task", item.id)
    except (InvalidTraining, TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return task_response(svc, user, item, True)


@router.delete("/training-tasks/{task_id}", status_code=204)
def delete_task(
    task_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> Response:
    require_same_origin(request)
    try:
        service(request).delete_task(user, task_id)
    except (TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return Response(status_code=204)


@router.post("/training-models/{model_id}/cancel", status_code=204)
def cancel_model(
    model_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> Response:
    require_same_origin(request)
    try:
        service(request).cancel_model(user, model_id)
    except (TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return Response(status_code=204)


@router.delete("/training-models/{model_id}", status_code=204)
def delete_model(
    model_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    confirm_published_model: bool = False,
) -> Response:
    require_same_origin(request)
    try:
        service(request).delete_model(
            user, model_id, confirm_published_model=confirm_published_model
        )
    except (TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return Response(status_code=204)


@router.post("/training-models/{model_id}/retry")
def retry_model(
    model_id: str,
    payload: ConfirmRetryRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    require_same_origin(request)
    try:
        svc = service(request)
        action = f"retry-model:{model_id}"
        previous = svc.idempotent_result(user, action, idempotency_key)
        if previous:
            with svc._session_factory() as db:
                run = db.get(TrainingRun, previous[1])
                db.expunge(run)
        else:
            run = svc.new_run(user, model_id, "retry", confirm_replace=payload.confirm_replace)
            svc.remember_idempotent_result(user, action, idempotency_key, "run", run.id)
    except (TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return run_response(run)


@router.post("/training-models/{model_id}/resume")
def resume_model(
    model_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    require_same_origin(request)
    try:
        svc = service(request)
        action = f"resume-model:{model_id}"
        previous = svc.idempotent_result(user, action, idempotency_key)
        if previous:
            with svc._session_factory() as db:
                run = db.get(TrainingRun, previous[1])
                db.expunge(run)
        else:
            run = svc.new_run(user, model_id, "resume")
            svc.remember_idempotent_result(user, action, idempotency_key, "run", run.id)
    except (TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return run_response(run)


@router.post("/training-models/{model_id}/derive", status_code=201)
def derive_model(
    model_id: str,
    payload: DeriveModelRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    require_same_origin(request)
    svc = service(request)
    try:
        action = f"derive-model:{model_id}"
        previous = svc.idempotent_result(user, action, idempotency_key)
        task = (
            svc.get_task(user, previous[1])
            if previous
            else svc.derive_model(user, model_id, **payload.model_dump())
        )
        svc.remember_idempotent_result(user, action, idempotency_key, "task", task.id)
    except (InvalidTraining, TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return task_response(svc, user, task, True)


@router.post("/training-models/{model_id}/extend", status_code=201)
def extend_model(
    model_id: str,
    payload: ExtendModelRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, object]:
    require_same_origin(request)
    svc = service(request)
    try:
        action = f"extend-model:{model_id}"
        previous = svc.idempotent_result(user, action, idempotency_key)
        task = (
            svc.get_task(user, previous[1])
            if previous
            else svc.extend_model(user, model_id, **payload.model_dump())
        )
        svc.remember_idempotent_result(user, action, idempotency_key, "task", task.id)
    except (InvalidTraining, TrainingConflict, TrainingForbidden, TrainingNotFound) as exc:
        _raise(exc)
    return task_response(svc, user, task, True)


@router.get("/training-runs/{run_id}/metrics")
def metrics(
    run_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    after_epoch: int = Query(0, ge=0),
) -> list[dict[str, object]]:
    return [
        {
            "epoch": row.epoch,
            "box_loss": row.box_loss,
            "cls_loss": row.cls_loss,
            "dfl_loss": row.dfl_loss,
            "learning_rate": row.learning_rate,
            "precision": row.precision,
            "recall": row.recall,
            "map50": row.map50,
            "map50_95": row.map50_95,
        }
        for row in service(request).metrics(run_id, after_epoch)
    ]


@router.get("/training-runs/{run_id}/log")
def log(
    run_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    cursor: int = Query(0, ge=0),
) -> dict[str, object]:
    svc = service(request)
    with svc._session_factory() as db:
        run = db.get(TrainingRun, run_id)
        if run is None:
            raise HTTPException(404, "training run not found")
        model = db.get(TrainingModel, run.training_model_id)
        task = db.get(TrainingTask, model.training_task_id)
        if task.deleted_at is not None:
            raise HTTPException(404, "training run not found")
        path = svc.workspace / run.storage_path / "train.log"
    if not path.is_file():
        return {"content": "", "next_cursor": cursor}
    content, next_cursor = terminal_snapshot(path)
    return {"content": content, "next_cursor": next_cursor}


def _run_path(request: Request, run_id: str) -> tuple[TrainingRun, Path]:
    svc = service(request)
    with svc._session_factory() as db:
        run = db.get(TrainingRun, run_id)
        if run is None:
            raise HTTPException(404, "training run not found")
        model = db.get(TrainingModel, run.training_model_id)
        task = db.get(TrainingTask, model.training_task_id) if model else None
        if task is None or task.deleted_at is not None:
            raise HTTPException(404, "training run not found")
        db.expunge(run)
    return run, svc.workspace / run.storage_path


@router.get("/training-runs/{run_id}/pr-curve")
def pr_curve(
    run_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> dict[str, object]:
    _, directory = _run_path(request, run_id)
    data = directory / "pr-curve.json"
    if data.is_file():
        try:
            return json.loads(data.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    return {"version": 1, "kind": "unavailable", "series": []}
