from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..models import User
from ..services.auto_annotations import (
    AutoAnnotationConflict,
    AutoAnnotationService,
    AutoAnnotationUnavailable,
)
from ..services.labels import InvalidLabel
from ..services.models import InvalidModel, ModelNotFound
from ..services.projects import ProjectForbidden, ProjectNotFound
from ..services.sampling import SamplingNotFound
from .annotations import AnnotationResponse
from .auth import current_user, require_same_origin
from .labels import LabelResponse, _label_response
from .media import TaskResponse, _task_response

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["auto-annotations"])


class RunAutoAnnotationRequest(BaseModel):
    source: Literal["local", "xanylabeling"] = "local"
    model_id: str = Field(min_length=1, max_length=255)
    remote_task_id: str | None = Field(default=None, max_length=128)
    categories: list[str] = Field(max_length=64)
    confidence: float = Field(ge=0, le=1)
    iou: float = Field(ge=0, le=1)


class RunBatchAutoAnnotationRequest(RunAutoAnnotationRequest):
    overwrite: bool = False


class DraftAnnotationResponse(AnnotationResponse):
    label_name: str


class AutoAnnotationResponse(BaseModel):
    items: list[DraftAnnotationResponse]
    created_labels: list[LabelResponse]


def auto_annotation_service(request: Request) -> AutoAnnotationService:
    service = request.app.state.auto_annotation_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def _raise_auto_error(exc: ValueError) -> NoReturn:
    if isinstance(exc, (ProjectNotFound, ModelNotFound, SamplingNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ProjectForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, AutoAnnotationUnavailable):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if isinstance(exc, AutoAnnotationConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post(
    "/videos/{video_id}/frames/{frame_id}/auto-annotations",
    response_model=AutoAnnotationResponse,
)
def run_frame_auto_annotation(
    project_id: str,
    video_id: str,
    frame_id: str,
    payload: RunAutoAnnotationRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> AutoAnnotationResponse:
    require_same_origin(request)
    try:
        result = auto_annotation_service(request).run_frame(
            user,
            project_id,
            video_id,
            frame_id,
            payload.model_id,
            payload.categories,
            payload.confidence,
            payload.iou,
            payload.source,
            payload.remote_task_id,
        )
    except (
        ProjectNotFound,
        ProjectForbidden,
        ModelNotFound,
        InvalidModel,
        SamplingNotFound,
        InvalidLabel,
        AutoAnnotationUnavailable,
    ) as exc:
        _raise_auto_error(exc)
    return AutoAnnotationResponse(
        items=[
            DraftAnnotationResponse(
                **item.annotation.__dict__,
                label_name=item.label_name,
            )
            for item in result.items
        ],
        created_labels=[_label_response(item) for item in result.created_labels],
    )


@router.post(
    "/videos/{video_id}/auto-annotations",
    response_model=TaskResponse,
    status_code=202,
)
def create_batch_auto_annotation(
    project_id: str,
    video_id: str,
    payload: RunBatchAutoAnnotationRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> TaskResponse:
    require_same_origin(request)
    try:
        task = auto_annotation_service(request).create_batch(
            user,
            project_id,
            video_id,
            payload.model_id,
            payload.categories,
            payload.confidence,
            payload.iou,
            payload.overwrite,
            payload.source,
            payload.remote_task_id,
        )
    except (
        ProjectNotFound,
        ProjectForbidden,
        ModelNotFound,
        InvalidModel,
        InvalidLabel,
        AutoAnnotationUnavailable,
        AutoAnnotationConflict,
    ) as exc:
        _raise_auto_error(exc)
    return _task_response(task)
