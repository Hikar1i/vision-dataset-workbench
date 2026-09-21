import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict

from ..models import EvaluationDataset, ModelEvaluation, User
from ..services.model_evaluations import (
    ZIP_LIMIT,
    ModelEvaluationConflict,
    ModelEvaluationError,
    ModelEvaluationForbidden,
    ModelEvaluationNotFound,
    ModelEvaluationService,
)
from .auth import current_user, require_same_origin
from .media import TaskResponse, _task_response

router = APIRouter(prefix="/api/v1", tags=["model-evaluations"])


class EvaluationDatasetResponse(BaseModel):
    id: str
    model_project_id: str
    name: str
    content_sha256: str | None
    classes: list[str]
    image_count: int
    label_count: int
    negative_count: int
    total_bytes: int
    status: Literal["queued", "validating", "ready", "failed"]
    task_id: str | None
    error: str | None
    created_at: str
    completed_at: str | None


class CreatedEvaluationDatasetResponse(BaseModel):
    dataset: EvaluationDatasetResponse
    task: TaskResponse


class CreateEvaluationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model_id: str
    dataset_id: str
    format: Literal["pt", "onnx", "engine"] = "pt"


class ModelEvaluationResponse(BaseModel):
    id: str
    model_project_id: str
    model_id: str
    model_name: str
    format: Literal["pt", "onnx", "engine"]
    evaluation_dataset_id: str
    dataset_name: str
    dataset_sha256: str
    class_mapping: dict[str, int]
    config: dict[str, object]
    metrics: dict[str, object]
    per_class_metrics: list[dict[str, object]]
    status: Literal["queued", "running", "succeeded", "failed", "canceled"]
    task_id: str | None
    error: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    has_confusion_matrix: bool
    has_pr_curve: bool
    model_deleted: bool
    dataset_deleted: bool


class CreatedEvaluationResponse(BaseModel):
    evaluation: ModelEvaluationResponse
    task: TaskResponse


def service(request: Request) -> ModelEvaluationService:
    value = request.app.state.model_evaluation_service
    if value is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return value


def _utc(value: datetime | None):
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def _dataset_response(value: EvaluationDataset):
    return EvaluationDatasetResponse(
        id=value.id,
        model_project_id=value.model_project_id,
        name=value.name,
        content_sha256=value.content_sha256,
        classes=json.loads(value.classes),
        image_count=value.image_count,
        label_count=value.label_count,
        negative_count=value.negative_count,
        total_bytes=value.total_bytes,
        status=value.status,
        task_id=value.task_id,
        error=value.error,
        created_at=_utc(value.created_at) or "",
        completed_at=_utc(value.completed_at),
    )


def _evaluation_response(value: ModelEvaluation, availability: dict[str, bool]):
    return ModelEvaluationResponse(
        id=value.id,
        model_project_id=value.model_project_id,
        model_id=value.model_id,
        model_name=value.model_name,
        format=value.format,
        evaluation_dataset_id=value.evaluation_dataset_id,
        dataset_name=value.dataset_name,
        dataset_sha256=value.dataset_sha256,
        class_mapping=json.loads(value.class_mapping),
        config=json.loads(value.config),
        metrics=json.loads(value.metrics),
        per_class_metrics=json.loads(value.per_class_metrics),
        status=value.status,
        task_id=value.task_id,
        error=value.error,
        created_at=_utc(value.created_at) or "",
        started_at=_utc(value.started_at),
        finished_at=_utc(value.finished_at),
        has_confusion_matrix=bool(value.confusion_matrix_path),
        has_pr_curve=bool(value.pr_curve_path),
        **availability,
    )


def _raise(exc: ModelEvaluationError) -> NoReturn:
    if isinstance(exc, ModelEvaluationNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ModelEvaluationForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ModelEvaluationConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get(
    "/model-projects/{project_id}/evaluation-datasets",
    response_model=list[EvaluationDatasetResponse],
)
def list_datasets(project_id: str, request: Request, user: Annotated[User, Depends(current_user)]):
    try:
        return [
            _dataset_response(item) for item in service(request).list_datasets(user, project_id)
        ]
    except ModelEvaluationError as exc:
        _raise(exc)


@router.post(
    "/model-projects/{project_id}/evaluation-datasets",
    response_model=CreatedEvaluationDatasetResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_dataset(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    name: Annotated[str, Query(min_length=1, max_length=128)],
    x_filename: Annotated[str, Header(max_length=512)] = "dataset.zip",
):
    require_same_origin(request)
    try:
        service(request).require_manage(user, project_id)
    except ModelEvaluationError as exc:
        _raise(exc)
    if Path(x_filename).suffix.lower() != ".zip":
        raise HTTPException(status_code=422, detail="只支持 ZIP 测试集")
    upload_root = service(request).workspace / "tmp" / "evaluation-api"
    upload_root.mkdir(parents=True, exist_ok=True)
    target = upload_root / f"{uuid4()}.zip"
    size = 0
    try:
        with target.open("xb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > ZIP_LIMIT:
                    raise ModelEvaluationError("ZIP 超过 1 GB")
                output.write(chunk)
        dataset, task = service(request).create_dataset(user, project_id, name, target)
        return CreatedEvaluationDatasetResponse(
            dataset=_dataset_response(dataset), task=_task_response(task)
        )
    except ModelEvaluationError as exc:
        _raise(exc)
    finally:
        target.unlink(missing_ok=True)


@router.delete("/evaluation-datasets/{dataset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_dataset(dataset_id: str, request: Request, user: Annotated[User, Depends(current_user)]):
    require_same_origin(request)
    try:
        service(request).delete_dataset(user, dataset_id)
    except ModelEvaluationError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.get(
    "/model-projects/{project_id}/evaluations", response_model=list[ModelEvaluationResponse]
)
def list_evaluations(
    project_id: str, request: Request, user: Annotated[User, Depends(current_user)]
):
    try:
        evaluation_service = service(request)
        return [
            _evaluation_response(item, evaluation_service.evaluation_availability(item))
            for item in evaluation_service.list_evaluations(user, project_id)
        ]
    except ModelEvaluationError as exc:
        _raise(exc)


@router.post(
    "/model-projects/{project_id}/evaluations",
    response_model=CreatedEvaluationResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_evaluation(
    project_id: str,
    payload: CreateEvaluationRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    require_same_origin(request)
    try:
        evaluation, task = service(request).create_evaluation(
            user, project_id, payload.model_id, payload.dataset_id, payload.format
        )
        return CreatedEvaluationResponse(
            evaluation=_evaluation_response(
                evaluation, {"model_deleted": False, "dataset_deleted": False}
            ),
            task=_task_response(task),
        )
    except ModelEvaluationError as exc:
        _raise(exc)


@router.get("/model-evaluations/{evaluation_id}", response_model=ModelEvaluationResponse)
def get_evaluation(
    evaluation_id: str, request: Request, user: Annotated[User, Depends(current_user)]
):
    try:
        evaluation_service = service(request)
        evaluation = evaluation_service.get_evaluation(user, evaluation_id)
        return _evaluation_response(
            evaluation, evaluation_service.evaluation_availability(evaluation)
        )
    except ModelEvaluationError as exc:
        _raise(exc)


@router.post("/model-evaluations/{evaluation_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_evaluation(
    evaluation_id: str, request: Request, user: Annotated[User, Depends(current_user)]
):
    require_same_origin(request)
    try:
        service(request).cancel(user, evaluation_id)
    except ModelEvaluationError as exc:
        _raise(exc)
    return Response(status_code=204)


@router.get("/model-evaluations/{evaluation_id}/plots/{kind}")
def evaluation_plot(
    evaluation_id: str,
    kind: Literal["confusion", "pr-curve"],
    request: Request,
    user: Annotated[User, Depends(current_user)],
):
    try:
        return FileResponse(service(request).result_file(user, evaluation_id, kind))
    except ModelEvaluationError as exc:
        _raise(exc)
