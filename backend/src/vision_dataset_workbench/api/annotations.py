from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..models import FrameAnnotation, User
from ..services.annotations import (
    AnnotationConflict,
    AnnotationInput,
    AnnotationNotFound,
    AnnotationService,
    InvalidAnnotation,
)
from ..services.projects import ProjectForbidden, ProjectNotFound
from .auth import current_user, require_same_origin

router = APIRouter(
    prefix=(
        "/api/v1/projects/{project_id}/videos/{video_id}/frames/{frame_id}/annotations"
    ),
    tags=["annotations"],
)


class AnnotationItem(BaseModel):
    id: str = Field(min_length=1, max_length=36)
    label_id: str = Field(min_length=1, max_length=36)
    x_min: int = Field(ge=0)
    y_min: int = Field(ge=0)
    x_max: int = Field(gt=0)
    y_max: int = Field(gt=0)
    source: Literal["manual", "model"] = "manual"
    confidence: float | None = Field(default=None, ge=0, le=1)


class ReplaceAnnotationsRequest(BaseModel):
    annotation_revision: int = Field(ge=1)
    items: list[AnnotationItem] = Field(max_length=10000)


class AnnotationResponse(AnnotationItem):
    pass


class FrameAnnotationsResponse(BaseModel):
    frame_id: str
    annotation_revision: int
    items: list[AnnotationResponse]


def annotation_service(request: Request) -> AnnotationService:
    service = request.app.state.annotation_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def _response(frame_id: str, revision: int, items: list[FrameAnnotation]):
    return FrameAnnotationsResponse(
        frame_id=frame_id,
        annotation_revision=revision,
        items=[
            AnnotationResponse(
                id=item.id,
                label_id=item.label_id,
                x_min=item.x_min,
                y_min=item.y_min,
                x_max=item.x_max,
                y_max=item.y_max,
                source=item.source,
                confidence=item.confidence,
            )
            for item in items
        ],
    )


def _raise_annotation_error(exc: ValueError) -> NoReturn:
    if isinstance(exc, (ProjectNotFound, AnnotationNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ProjectForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, AnnotationConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=FrameAnnotationsResponse)
def list_frame_annotations(
    project_id: str,
    video_id: str,
    frame_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FrameAnnotationsResponse:
    try:
        frame, items = annotation_service(request).list_frame(
            user, project_id, video_id, frame_id
        )
    except (ProjectNotFound, ProjectForbidden, AnnotationNotFound) as exc:
        _raise_annotation_error(exc)
    return _response(frame.id, frame.annotation_revision, items)


@router.put("", response_model=FrameAnnotationsResponse)
def replace_frame_annotations(
    project_id: str,
    video_id: str,
    frame_id: str,
    payload: ReplaceAnnotationsRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FrameAnnotationsResponse:
    require_same_origin(request)
    try:
        frame, items = annotation_service(request).replace_frame(
            user,
            project_id,
            video_id,
            frame_id,
            payload.annotation_revision,
            [AnnotationInput(**item.model_dump()) for item in payload.items],
        )
    except (
        ProjectNotFound,
        ProjectForbidden,
        AnnotationNotFound,
        AnnotationConflict,
        InvalidAnnotation,
    ) as exc:
        _raise_annotation_error(exc)
    return _response(frame.id, frame.annotation_revision, items)
