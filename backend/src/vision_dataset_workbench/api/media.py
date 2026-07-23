import json
from datetime import datetime, timezone
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ..media import InvalidMediaSource, MediaToolError, RemotePreview
from ..models import Task, User, Video
from ..services.media import (
    ImportBatch,
    MediaConflict,
    MediaNotFound,
    MediaService,
)
from ..services.projects import ProjectForbidden, ProjectNotFound
from ..storage.paths import UnsafePathError
from .auth import current_user, require_same_origin

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["media"])


class LocalPreviewRequest(BaseModel):
    path: str = Field(min_length=1, max_length=2048)


class LocalImportRequest(BaseModel):
    paths: list[str] = Field(min_length=1, max_length=999)


class RemotePreviewRequest(BaseModel):
    url: str = Field(min_length=1, max_length=4096)


class RemoteImportItem(BaseModel):
    title: str = Field(default="Remote video", max_length=512)
    url: str = Field(min_length=1, max_length=4096)


class RemoteImportRequest(BaseModel):
    items: list[RemoteImportItem] = Field(min_length=1, max_length=999)


class LocalPreviewResponse(BaseModel):
    path: str
    name: str
    size: int


class RemotePreviewResponse(BaseModel):
    title: str
    url: str
    duration: float
    extractor: str
    external_id: str
    playlist: str
    playlist_index: int | None


class VideoResponse(BaseModel):
    id: str
    source_type: str
    title: str
    source_name: str | None
    source_url: str | None
    duration: float
    width: int
    height: int
    fps: float
    total_frames: int
    file_size: int
    status: str
    version: int
    created_at: str
    updated_at: str


class TaskResponse(BaseModel):
    id: str
    video_id: str | None
    type: str
    status: str
    progress: int
    error: str | None
    result: dict[str, object] | None
    cancel_requested: bool
    attempts: int
    retry_of_id: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None
    updated_at: str


class AcceptedResponse(BaseModel):
    video: VideoResponse
    task: TaskResponse


class NoticeResponse(BaseModel):
    input: str
    reason: str


class ImportBatchResponse(BaseModel):
    accepted: list[AcceptedResponse]
    skipped: list[NoticeResponse]
    rejected: list[NoticeResponse]


class VideoPageResponse(BaseModel):
    items: list[VideoResponse]
    page: int
    page_size: int
    total: int


class TaskPageResponse(BaseModel):
    items: list[TaskResponse]
    page: int
    page_size: int
    total: int


def media_service(request: Request) -> MediaService:
    service = request.app.state.media_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def _utc_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def _video_response(video: Video) -> VideoResponse:
    return VideoResponse(
        id=video.id,
        source_type=video.source_type,
        title=video.title,
        source_name=video.source_name,
        source_url=video.source_url,
        duration=video.duration,
        width=video.width,
        height=video.height,
        fps=video.fps,
        total_frames=video.total_frames,
        file_size=video.file_size,
        status=video.status,
        version=video.version,
        created_at=_utc_text(video.created_at) or "",
        updated_at=_utc_text(video.updated_at) or "",
    )


def _task_response(task: Task) -> TaskResponse:
    result = json.loads(task.result) if task.result else None
    return TaskResponse(
        id=task.id,
        video_id=task.video_id,
        type=task.type,
        status=task.status,
        progress=task.progress,
        error=task.error,
        result=result,
        cancel_requested=task.cancel_requested,
        attempts=task.attempts,
        retry_of_id=task.retry_of_id,
        created_at=_utc_text(task.created_at) or "",
        started_at=_utc_text(task.started_at),
        finished_at=_utc_text(task.finished_at),
        updated_at=_utc_text(task.updated_at) or "",
    )


def _batch_response(batch: ImportBatch) -> ImportBatchResponse:
    return ImportBatchResponse(
        accepted=[
            AcceptedResponse(
                video=_video_response(item.video), task=_task_response(item.task)
            )
            for item in batch.accepted
        ],
        skipped=[NoticeResponse(input=item.input, reason=item.reason) for item in batch.skipped],
        rejected=[
            NoticeResponse(input=item.input, reason=item.reason) for item in batch.rejected
        ],
    )


def _raise_media_error(exc: Exception) -> NoReturn:
    if isinstance(exc, (ProjectNotFound, MediaNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ProjectForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, MediaConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/videos", response_model=VideoPageResponse)
def list_videos(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> VideoPageResponse:
    try:
        items, total = media_service(request).list_videos(
            user, project_id, page=page, page_size=page_size
        )
    except (ProjectNotFound, ProjectForbidden) as exc:
        _raise_media_error(exc)
    return VideoPageResponse(
        items=[_video_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/imports/local/preview", response_model=list[LocalPreviewResponse])
def preview_local(
    project_id: str,
    payload: LocalPreviewRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[LocalPreviewResponse]:
    require_same_origin(request)
    try:
        items = media_service(request).preview_local(user, project_id, payload.path)
    except (ProjectNotFound, ProjectForbidden, OSError, UnsafePathError) as exc:
        _raise_media_error(exc)
    return [LocalPreviewResponse(path=item.path, name=item.name, size=item.size) for item in items]


@router.post(
    "/imports/local", response_model=ImportBatchResponse, status_code=status.HTTP_202_ACCEPTED
)
def import_local(
    project_id: str,
    payload: LocalImportRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> ImportBatchResponse:
    require_same_origin(request)
    try:
        batch = media_service(request).import_local(user, project_id, payload.paths)
    except (ProjectNotFound, ProjectForbidden) as exc:
        _raise_media_error(exc)
    return _batch_response(batch)


@router.post("/imports/remote/preview", response_model=list[RemotePreviewResponse])
def preview_remote_items(
    project_id: str,
    payload: RemotePreviewRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[RemotePreview]:
    require_same_origin(request)
    try:
        return media_service(request).preview_remote(user, project_id, payload.url)
    except (
        ProjectNotFound,
        ProjectForbidden,
        InvalidMediaSource,
        MediaToolError,
    ) as exc:
        _raise_media_error(exc)


@router.post(
    "/imports/remote", response_model=ImportBatchResponse, status_code=status.HTTP_202_ACCEPTED
)
def import_remote(
    project_id: str,
    payload: RemoteImportRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> ImportBatchResponse:
    require_same_origin(request)
    try:
        batch = media_service(request).import_remote(
            user, project_id, [(item.title, item.url) for item in payload.items]
        )
    except (ProjectNotFound, ProjectForbidden) as exc:
        _raise_media_error(exc)
    return _batch_response(batch)


@router.get("/tasks", response_model=TaskPageResponse)
def list_tasks(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> TaskPageResponse:
    try:
        items, total = media_service(request).list_tasks(
            user, project_id, page=page, page_size=page_size
        )
    except (ProjectNotFound, ProjectForbidden) as exc:
        _raise_media_error(exc)
    return TaskPageResponse(
        items=[_task_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/tasks/{task_id}/cancel", response_model=TaskResponse)
def cancel_task(
    project_id: str,
    task_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> TaskResponse:
    require_same_origin(request)
    try:
        task = media_service(request).cancel_task(user, project_id, task_id)
    except (ProjectNotFound, ProjectForbidden, MediaNotFound, MediaConflict) as exc:
        _raise_media_error(exc)
    return _task_response(task)


@router.post(
    "/tasks/{task_id}/retry",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
def retry_task(
    project_id: str,
    task_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> TaskResponse:
    require_same_origin(request)
    try:
        task = media_service(request).retry_task(user, project_id, task_id)
    except (ProjectNotFound, ProjectForbidden, MediaNotFound, MediaConflict) as exc:
        _raise_media_error(exc)
    return _task_response(task)
