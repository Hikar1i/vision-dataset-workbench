import json
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ..models import DatasetExport, User
from ..services.dataset_exports import (
    DatasetExportConflict,
    DatasetExportNotFound,
    DatasetExportService,
    ExportLabelInput,
    InvalidDatasetExport,
)
from ..services.projects import ProjectForbidden, ProjectNotFound
from .auth import current_user, require_same_origin
from .projects import _utc_text

router = APIRouter(
    prefix="/api/v1/projects/{project_id}/dataset-exports",
    tags=["dataset-exports"],
)


class ExportLabelRequest(BaseModel):
    source_label_id: str = Field(min_length=1, max_length=36)
    name: str = Field(min_length=1, max_length=64)
    mapping: int = Field(ge=0)
    enabled: bool


class CreateDatasetExportRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    train_ratio: float = Field(ge=0, le=1)
    labels: list[ExportLabelRequest] = Field(min_length=1, max_length=10000)


class ExportLabelResponse(BaseModel):
    source_label_id: str
    name: str
    mapping: int
    enabled: bool


class DatasetExportResponse(BaseModel):
    id: str
    project_id: str
    task_id: str | None
    name: str
    status: str
    train_ratio: float
    actual_train_ratio: float | None
    total_frames: int
    train_frames: int
    val_frames: int
    labels: list[ExportLabelResponse]
    error: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None


class DatasetExportDetailResponse(DatasetExportResponse):
    absolute_path: str | None
    manifest: dict[str, object] | None


class DatasetExportPageResponse(BaseModel):
    items: list[DatasetExportResponse]
    page: int
    page_size: int
    total: int


def dataset_export_service(request: Request) -> DatasetExportService:
    service = request.app.state.dataset_export_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def _raise_http_error(exc: ValueError) -> NoReturn:
    if isinstance(exc, (ProjectNotFound, DatasetExportNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ProjectForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, DatasetExportConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


def _response(record: DatasetExport) -> DatasetExportResponse:
    return DatasetExportResponse(
        id=record.id,
        project_id=record.project_id,
        task_id=record.task_id,
        name=record.name,
        status=record.status,
        train_ratio=record.train_ratio,
        actual_train_ratio=record.actual_train_ratio,
        total_frames=record.total_frames,
        train_frames=record.train_frames,
        val_frames=record.val_frames,
        labels=[ExportLabelResponse(**item) for item in json.loads(record.label_snapshot)],
        error=record.error,
        created_at=_utc_text(record.created_at),
        started_at=_utc_text(record.started_at) if record.started_at else None,
        completed_at=_utc_text(record.completed_at) if record.completed_at else None,
    )


@router.post("", response_model=DatasetExportResponse, status_code=status.HTTP_202_ACCEPTED)
def create_dataset_export(
    project_id: str,
    payload: CreateDatasetExportRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> DatasetExportResponse:
    require_same_origin(request)
    try:
        record = dataset_export_service(request).create(
            user,
            project_id,
            payload.name,
            payload.train_ratio,
            [ExportLabelInput(**item.model_dump()) for item in payload.labels],
        )
    except (ProjectNotFound, ProjectForbidden, DatasetExportConflict, InvalidDatasetExport) as exc:
        _raise_http_error(exc)
    return _response(record)


@router.get("", response_model=DatasetExportPageResponse)
def list_dataset_exports(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> DatasetExportPageResponse:
    try:
        items, total = dataset_export_service(request).list_exports(
            user, project_id, page=page, page_size=page_size
        )
    except (ProjectNotFound, ProjectForbidden) as exc:
        _raise_http_error(exc)
    return DatasetExportPageResponse(
        items=[_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.get("/{export_id}", response_model=DatasetExportDetailResponse)
def get_dataset_export(
    project_id: str,
    export_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> DatasetExportDetailResponse:
    try:
        record = dataset_export_service(request).get(user, project_id, export_id)
    except (ProjectNotFound, ProjectForbidden, DatasetExportNotFound) as exc:
        _raise_http_error(exc)
    response = _response(record).model_dump()
    absolute_path = None
    if record.storage_path:
        absolute_path = str((request.app.state.workspace / record.storage_path).resolve())
    return DatasetExportDetailResponse(
        **response,
        absolute_path=absolute_path,
        manifest=json.loads(record.manifest) if record.manifest else None,
    )
