import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..media import InvalidMediaSource, MediaToolError, RemotePreview
from ..models import Task, User, Video
from ..services.media import (
    ImportBatch,
    MediaConflict,
    MediaNotFound,
    MediaService,
    MediaUnavailable,
)
from ..services.projects import ProjectForbidden, ProjectNotFound
from ..services.sampling import SamplingSummary
from ..storage.paths import UnsafePathError
from .auth import current_user, require_same_origin

router = APIRouter(prefix="/api/v1/projects/{project_id}", tags=["media"])
global_task_router = APIRouter(prefix="/api/v1", tags=["tasks"])


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


class SamplingSummaryResponse(BaseModel):
    id: str
    state: str
    mode: str
    parameters: dict[str, int]
    output_format: str
    output_quality: int
    computed_interval: int | None
    expected_frames: int
    extracted_frames: int
    enabled_frames: int
    version: int
    applied_version: int
    generation: int
    frame_revision: int
    updated_at: str


class TaskResponse(BaseModel):
    id: str
    project_id: str
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


class VideoResponse(BaseModel):
    id: str
    short_code: str
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
    enabled: bool
    version: int
    created_at: str
    updated_at: str
    sampling: SamplingSummaryResponse | None = None
    latest_task: TaskResponse | None = None


class VideoEnabledRequest(BaseModel):
    enabled: bool
    version: int = Field(ge=1)


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


class GlobalTaskResponse(TaskResponse):
    project_name: str
    can_manage: bool


class GlobalTaskPageResponse(BaseModel):
    items: list[GlobalTaskResponse]
    page: int
    page_size: int
    total: int
    latest_terminal_at: str | None


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


def _sampling_response(summary: SamplingSummary) -> SamplingSummaryResponse:
    return SamplingSummaryResponse(
        **{**summary.__dict__, "updated_at": _utc_text(summary.updated_at) or ""}
    )


def _video_response(
    video: Video,
    summary: SamplingSummary | None = None,
    latest_task: Task | None = None,
) -> VideoResponse:
    return VideoResponse(
        id=video.id,
        short_code=video.short_code,
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
        enabled=video.enabled,
        version=video.version,
        created_at=_utc_text(video.created_at) or "",
        updated_at=_utc_text(video.updated_at) or "",
        sampling=_sampling_response(summary) if summary else None,
        latest_task=_task_response(latest_task) if latest_task else None,
    )


def _task_response(task: Task) -> TaskResponse:
    result = json.loads(task.result) if task.result else None
    return TaskResponse(
        id=task.id,
        project_id=task.project_id,
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


@global_task_router.get("/tasks", response_model=GlobalTaskPageResponse)
def list_global_tasks(
    request: Request,
    user: Annotated[User, Depends(current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> GlobalTaskPageResponse:
    items, total, latest_terminal_at = media_service(request).list_visible_tasks(
        user, page=page, page_size=page_size
    )
    return GlobalTaskPageResponse(
        items=[
            GlobalTaskResponse(
                **_task_response(item.task).model_dump(),
                project_name=item.project_name,
                can_manage=item.can_manage,
            )
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
        latest_terminal_at=_utc_text(latest_terminal_at),
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
    if isinstance(exc, MediaUnavailable):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/videos", response_model=VideoPageResponse)
def list_videos(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=999)] = 50,
) -> VideoPageResponse:
    service = media_service(request)
    try:
        items, total = service.list_videos(
            user, project_id, page=page, page_size=page_size
        )
    except (ProjectNotFound, ProjectForbidden) as exc:
        _raise_media_error(exc)
    summaries = request.app.state.sampling_service.summaries(
        user, project_id, [item.id for item in items]
    )
    latest_tasks = service.latest_tasks(user, project_id, [item.id for item in items])
    return VideoPageResponse(
        items=[
            _video_response(
                item,
                summaries.get(item.id),
                latest_tasks.get(item.id),
            )
            for item in items
        ],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.put("/videos/{video_id}/enabled", response_model=VideoResponse)
def update_video_enabled(
    project_id: str,
    video_id: str,
    payload: VideoEnabledRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> VideoResponse:
    require_same_origin(request)
    try:
        video = media_service(request).update_enabled(
            user,
            project_id,
            video_id,
            enabled=payload.enabled,
            version=payload.version,
        )
    except (ProjectNotFound, ProjectForbidden, MediaNotFound, MediaConflict) as exc:
        _raise_media_error(exc)
    return _video_response(video)


def _video_file(
    project_id: str,
    video_id: str,
    request: Request,
    user: User,
    *,
    thumbnail: bool = False,
) -> tuple[Video, str]:
    try:
        video, path = media_service(request).ready_video_file(
            user, project_id, video_id, thumbnail=thumbnail
        )
    except (ProjectNotFound, ProjectForbidden, MediaNotFound, MediaConflict) as exc:
        _raise_media_error(exc)
    return video, str(path)


@router.get("/videos/{video_id}/content", response_class=FileResponse)
def video_content(
    project_id: str,
    video_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FileResponse:
    _video, path = _video_file(project_id, video_id, request, user)
    return FileResponse(path)


@router.get("/videos/{video_id}/download", response_class=FileResponse)
def download_video(
    project_id: str,
    video_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FileResponse:
    video, path = _video_file(project_id, video_id, request, user)
    suffix = Path(path).suffix
    return FileResponse(path, filename=video.source_name or f"{video.title}{suffix}")


@router.get("/videos/{video_id}/thumbnail", response_class=FileResponse)
def video_thumbnail(
    project_id: str,
    video_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FileResponse:
    _video, path = _video_file(
        project_id, video_id, request, user, thumbnail=True
    )
    return FileResponse(path, media_type="image/jpeg")


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
    except (ProjectNotFound, ProjectForbidden, MediaUnavailable) as exc:
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
    except (ProjectNotFound, ProjectForbidden, MediaUnavailable) as exc:
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
