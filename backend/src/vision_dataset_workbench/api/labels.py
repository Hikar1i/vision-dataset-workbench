from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..models import ProjectLabel, User
from ..services.labels import (
    InvalidLabel,
    LabelChanges,
    LabelConflict,
    LabelNotFound,
    LabelService,
)
from ..services.projects import ProjectForbidden, ProjectNotFound
from .auth import current_user, require_same_origin
from .projects import _utc_text

router = APIRouter(prefix="/api/v1/projects/{project_id}/labels", tags=["labels"])


class CreateLabelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    description_zh: str = Field(default="", max_length=64)
    color: str = Field(pattern=r"^#[0-9A-Fa-f]{6}$")


class UpdateLabelRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=64)
    description_zh: str | None = Field(default=None, max_length=64)
    color: str | None = Field(default=None, pattern=r"^#[0-9A-Fa-f]{6}$")
    enabled: bool | None = None
    version: int = Field(ge=1)


class ReorderLabelsRequest(BaseModel):
    label_ids: list[str]


class LabelResponse(BaseModel):
    id: str
    name: str
    description_zh: str
    color: str
    sort_order: int
    enabled: bool
    version: int
    created_at: str
    updated_at: str


def label_service(request: Request) -> LabelService:
    service = request.app.state.label_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def _label_response(label: ProjectLabel) -> LabelResponse:
    return LabelResponse(
        id=label.id,
        name=label.name,
        description_zh=label.description_zh,
        color=label.color,
        sort_order=label.sort_order,
        enabled=label.enabled,
        version=label.version,
        created_at=_utc_text(label.created_at),
        updated_at=_utc_text(label.updated_at),
    )


def _raise_http_error(exc: ValueError) -> NoReturn:
    if isinstance(exc, (ProjectNotFound, LabelNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ProjectForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, LabelConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=list[LabelResponse])
def list_labels(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[LabelResponse]:
    try:
        labels = label_service(request).list_labels(user, project_id)
    except ValueError as exc:
        _raise_http_error(exc)
    return [_label_response(label) for label in labels]


@router.post("", response_model=LabelResponse, status_code=status.HTTP_201_CREATED)
def create_label(
    project_id: str,
    payload: CreateLabelRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> LabelResponse:
    require_same_origin(request)
    try:
        label = label_service(request).create_label(
            user,
            project_id,
            payload.name,
            payload.description_zh,
            payload.color,
        )
    except (InvalidLabel, LabelConflict, ProjectNotFound, ProjectForbidden) as exc:
        _raise_http_error(exc)
    return _label_response(label)


@router.put("/order", response_model=list[LabelResponse])
def reorder_labels(
    project_id: str,
    payload: ReorderLabelsRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[LabelResponse]:
    require_same_origin(request)
    try:
        labels = label_service(request).reorder_labels(
            user, project_id, payload.label_ids
        )
    except (InvalidLabel, ProjectNotFound, ProjectForbidden) as exc:
        _raise_http_error(exc)
    return [_label_response(label) for label in labels]


@router.patch("/{label_id}", response_model=LabelResponse)
def update_label(
    project_id: str,
    label_id: str,
    payload: UpdateLabelRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> LabelResponse:
    require_same_origin(request)
    try:
        label = label_service(request).update_label(
            user,
            project_id,
            label_id,
            LabelChanges(
                name=payload.name,
                description_zh=payload.description_zh,
                color=payload.color,
                enabled=payload.enabled,
            ),
            version=payload.version,
        )
    except (
        InvalidLabel,
        LabelConflict,
        LabelNotFound,
        ProjectNotFound,
        ProjectForbidden,
    ) as exc:
        _raise_http_error(exc)
    return _label_response(label)


@router.delete("/{label_id}", status_code=204)
def delete_label(
    project_id: str,
    label_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> None:
    require_same_origin(request)
    try:
        label_service(request).delete_label(user, project_id, label_id)
    except (LabelNotFound, LabelConflict, ProjectNotFound, ProjectForbidden) as exc:
        _raise_http_error(exc)
