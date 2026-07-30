from datetime import datetime, timezone
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field, field_validator

from ..models import Frame, FrameAnnotation, SamplingPlan, User
from ..sampling import InvalidSampling, SamplingInput
from ..services.projects import ProjectForbidden, ProjectNotFound
from ..services.sampling import (
    SamplingConflict,
    SamplingNotFound,
    SamplingService,
    sampling_summary,
)
from .auth import current_user, require_same_origin
from .media import (
    SamplingSummaryResponse,
    TaskResponse,
    _sampling_response,
    _task_response,
)

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["sampling"])


class ConfigureSamplingRequest(BaseModel):
    video_ids: list[str] = Field(min_length=1, max_length=999)
    mode: Literal["target_frames", "frame_interval", "time_interval"]
    parameters: dict[str, int]
    output_format: Literal["jpg", "png"] = "jpg"
    output_quality: int = Field(default=2, ge=0, le=31)
    overwrite_level: Literal["none", "configured", "sampled"] = "none"


class ExtractionRequest(BaseModel):
    video_ids: list[str] = Field(min_length=1, max_length=999)
    overwrite_level: Literal["none", "light", "destructive"] = "none"


class SamplingNoticeResponse(BaseModel):
    input: str
    reason: str
    code: str


class AcceptedPlanResponse(BaseModel):
    video_id: str
    plan: SamplingSummaryResponse


class PlanBatchResponse(BaseModel):
    accepted: list[AcceptedPlanResponse]
    rejected: list[SamplingNoticeResponse]


class AcceptedExtractionResponse(BaseModel):
    video_id: str
    task: TaskResponse


class ExtractionBatchResponse(BaseModel):
    accepted: list[AcceptedExtractionResponse]
    rejected: list[SamplingNoticeResponse]


class FrameResponse(BaseModel):
    id: str
    sequence: int
    source_frame_index: int
    time_offset: float
    enabled: bool
    file_size: int
    created_at: str
    annotations: list["FramePreviewAnnotationResponse"] | None = None


class FramePreviewAnnotationResponse(BaseModel):
    id: str
    label_id: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int


class FramePageResponse(BaseModel):
    items: list[FrameResponse]
    page: int
    page_size: int
    total: int
    sampling: SamplingSummaryResponse


class FrameEnabledChangeRequest(BaseModel):
    frame_id: str = Field(min_length=1, max_length=36)
    enabled: bool


class SetFramesEnabledRequest(BaseModel):
    changes: list[FrameEnabledChangeRequest] = Field(min_length=1)
    frame_revision: int = Field(ge=0)

    @field_validator("changes")
    @classmethod
    def unique_frame_ids(
        cls, changes: list[FrameEnabledChangeRequest]
    ) -> list[FrameEnabledChangeRequest]:
        if len({item.frame_id for item in changes}) != len(changes):
            raise ValueError("frame ids must be unique")
        return changes


class FrameAnnotationSummaryResponse(BaseModel):
    annotated_frame_ids: list[str]


def sampling_service(request: Request) -> SamplingService:
    service = request.app.state.sampling_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def _utc_text(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def _frame_response(
    frame: Frame,
    workspace,
    annotations: list[FrameAnnotation] | None = None,
) -> FrameResponse:
    try:
        file_size = (workspace / frame.file_path).stat().st_size
    except OSError:
        file_size = 0
    return FrameResponse(
        id=frame.id,
        sequence=frame.sequence,
        source_frame_index=frame.source_frame_index,
        time_offset=frame.time_offset,
        enabled=frame.enabled,
        file_size=file_size,
        created_at=_utc_text(frame.created_at),
        annotations=(
            [
                FramePreviewAnnotationResponse(
                    id=item.id,
                    label_id=item.label_id,
                    x_min=item.x_min,
                    y_min=item.y_min,
                    x_max=item.x_max,
                    y_max=item.y_max,
                )
                for item in annotations
            ]
            if annotations is not None
            else None
        ),
    )


def _plan_response(plan: SamplingPlan) -> SamplingSummaryResponse:
    return _sampling_response(sampling_summary(plan))


def _raise_sampling_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (ProjectNotFound, SamplingNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ProjectForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, SamplingConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/sampling-plans", response_model=PlanBatchResponse)
def configure_sampling(
    project_id: str,
    payload: ConfigureSamplingRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> PlanBatchResponse:
    require_same_origin(request)
    try:
        batch = sampling_service(request).configure(
            user,
            project_id,
            payload.video_ids,
            SamplingInput(payload.mode, payload.parameters),
            payload.output_format,
            payload.output_quality,
            payload.overwrite_level,
        )
    except (ProjectNotFound, ProjectForbidden, InvalidSampling, ValueError) as exc:
        _raise_sampling_error(exc)
    return PlanBatchResponse(
        accepted=[
            AcceptedPlanResponse(video_id=item.video_id, plan=_plan_response(item.plan))
            for item in batch.accepted
        ],
        rejected=[SamplingNoticeResponse(**item.__dict__) for item in batch.rejected],
    )


@router.post(
    "/extractions",
    response_model=ExtractionBatchResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_extractions(
    project_id: str,
    payload: ExtractionRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> ExtractionBatchResponse:
    require_same_origin(request)
    try:
        batch = sampling_service(request).create_extractions(
            user, project_id, payload.video_ids, payload.overwrite_level
        )
    except (ProjectNotFound, ProjectForbidden, ValueError) as exc:
        _raise_sampling_error(exc)
    return ExtractionBatchResponse(
        accepted=[
            AcceptedExtractionResponse(
                video_id=item.video_id, task=_task_response(item.task)
            )
            for item in batch.accepted
        ],
        rejected=[SamplingNoticeResponse(**item.__dict__) for item in batch.rejected],
    )


@router.get(
    "/videos/{video_id}/sampling-plan", response_model=SamplingSummaryResponse
)
def get_sampling_plan(
    project_id: str,
    video_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> SamplingSummaryResponse:
    try:
        plan = sampling_service(request).get_plan(user, project_id, video_id)
        if plan is None:
            raise SamplingNotFound("sampling plan not found")
    except (ProjectNotFound, ProjectForbidden, SamplingNotFound) as exc:
        _raise_sampling_error(exc)
    return _plan_response(plan)


@router.get(
    "/videos/{video_id}/frames",
    response_model=FramePageResponse,
    response_model_exclude_none=True,
)
def list_frames(
    project_id: str,
    video_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
    enabled: bool | None = None,
    include_annotations: bool = False,
) -> FramePageResponse:
    try:
        items, total, plan = sampling_service(request).list_frames(
            user,
            project_id,
            video_id,
            page=page,
            page_size=page_size,
            enabled=enabled,
        )
    except (ProjectNotFound, ProjectForbidden, SamplingNotFound) as exc:
        _raise_sampling_error(exc)
    previews = (
        sampling_service(request).frame_annotation_previews(
            user,
            project_id,
            video_id,
            [item.id for item in items],
        )
        if include_annotations
        else {}
    )
    return FramePageResponse(
        items=[
            _frame_response(
                item,
                request.app.state.workspace,
                previews.get(item.id, []) if include_annotations else None,
            )
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
        sampling=_plan_response(plan),
    )


@router.get(
    "/videos/{video_id}/frames/annotation-summary",
    response_model=FrameAnnotationSummaryResponse,
)
def frame_annotation_summary(
    project_id: str,
    video_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FrameAnnotationSummaryResponse:
    try:
        frame_ids = sampling_service(request).annotated_frame_ids(
            user, project_id, video_id
        )
    except (ProjectNotFound, ProjectForbidden, SamplingNotFound) as exc:
        _raise_sampling_error(exc)
    return FrameAnnotationSummaryResponse(annotated_frame_ids=frame_ids)


@router.get("/videos/{video_id}/frames/{frame_id}/image")
def frame_image(
    project_id: str,
    video_id: str,
    frame_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FileResponse:
    try:
        _frame, path = sampling_service(request).ready_frame_file(
            user, project_id, video_id, frame_id
        )
    except (ProjectNotFound, ProjectForbidden, SamplingNotFound) as exc:
        _raise_sampling_error(exc)
    media_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    return FileResponse(str(path), media_type=media_type)


@router.put(
    "/videos/{video_id}/frames/enabled", response_model=SamplingSummaryResponse
)
def set_frames_enabled(
    project_id: str,
    video_id: str,
    payload: SetFramesEnabledRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> SamplingSummaryResponse:
    require_same_origin(request)
    try:
        plan = sampling_service(request).set_frames_enabled(
            user,
            project_id,
            video_id,
            {item.frame_id: item.enabled for item in payload.changes},
            revision=payload.frame_revision,
        )
    except (
        ProjectNotFound,
        ProjectForbidden,
        SamplingNotFound,
        SamplingConflict,
    ) as exc:
        _raise_sampling_error(exc)
    return _plan_response(plan)
