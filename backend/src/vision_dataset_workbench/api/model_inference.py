import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Annotated, Literal, NoReturn
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..models import ModelInferenceRun, User
from ..services.model_inference import (
    IMAGE_LIMIT,
    VIDEO_LIMIT,
    ModelInferenceConflict,
    ModelInferenceError,
    ModelInferenceForbidden,
    ModelInferenceNotFound,
    ModelInferenceService,
)
from .auth import current_user, require_same_origin

router = APIRouter(prefix="/api/v1", tags=["model-inference"])


class ModelInferenceResponse(BaseModel):
    id: str
    model_id: str
    format: Literal["pt", "onnx", "engine"]
    input_type: Literal["image", "video"]
    status: Literal["queued", "running", "succeeded", "failed", "canceled"]
    parameters: dict[str, object]
    statistics: dict[str, object]
    task_id: str | None
    error: str | None
    saved_at: str | None
    expires_at: str | None
    created_at: str
    started_at: str | None
    finished_at: str | None


def service(request: Request) -> ModelInferenceService:
    value = request.app.state.model_inference_service
    if value is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return value


def _utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def _response(run: ModelInferenceRun) -> ModelInferenceResponse:
    return ModelInferenceResponse(
        id=run.id,
        model_id=run.model_id,
        format=run.format,
        input_type=run.input_type,
        status=run.status,
        parameters=json.loads(run.parameters),
        statistics=json.loads(run.statistics),
        task_id=run.task_id,
        error=run.error,
        saved_at=_utc(run.saved_at),
        expires_at=_utc(run.expires_at),
        created_at=_utc(run.created_at) or "",
        started_at=_utc(run.started_at),
        finished_at=_utc(run.finished_at),
    )


def _raise(exc: ModelInferenceError) -> NoReturn:
    if isinstance(exc, ModelInferenceNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ModelInferenceForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ModelInferenceConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/models/{model_id}/inference/current", response_model=ModelInferenceResponse | None)
def current_inference(
    model_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> ModelInferenceResponse | None:
    try:
        run = service(request).current(user, model_id)
        return _response(run) if run else None
    except ModelInferenceError as exc:
        _raise(exc)


@router.get("/models/{model_id}/inference/saved", response_model=list[ModelInferenceResponse])
def saved_inference(
    model_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[ModelInferenceResponse]:
    try:
        return [_response(item) for item in service(request).saved(user, model_id)]
    except ModelInferenceError as exc:
        _raise(exc)


@router.post(
    "/models/{model_id}/inference",
    response_model=ModelInferenceResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_inference(
    model_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
    input_type: Annotated[Literal["image", "video"], Query()],
    format: Annotated[Literal["pt", "onnx", "engine"], Query()] = "pt",
    confidence: Annotated[float, Query(ge=0, le=1)] = 0.25,
    iou: Annotated[float, Query(ge=0, le=1)] = 0.7,
    image_size: Annotated[int, Query(ge=32, le=8192, multiple_of=32)] = 640,
    max_det: Annotated[int, Query(ge=1, le=3000)] = 300,
    stride: Annotated[int, Query(ge=1, le=120)] = 1,
    x_filename: Annotated[str, Header(max_length=512)] = "upload",
    x_replace_inference: Annotated[bool, Header()] = False,
) -> ModelInferenceResponse:
    require_same_origin(request)
    limit = IMAGE_LIMIT if input_type == "image" else VIDEO_LIMIT
    upload_root = service(request).workspace / "tmp" / "inference-uploads"
    upload_root.mkdir(parents=True, exist_ok=True)
    target = upload_root / str(uuid4())
    size = 0
    try:
        with target.open("xb") as output:
            async for chunk in request.stream():
                size += len(chunk)
                if size > limit:
                    raise ModelInferenceError(f"文件超过 {limit // 1024 // 1024} MB 限制")
                output.write(chunk)
        run = service(request).create(
            user,
            model_id,
            input_type,
            format,
            target,
            Path(x_filename).name,
            {
                "confidence": confidence,
                "iou": iou,
                "image_size": image_size,
                "max_det": max_det,
                "stride": stride,
            },
            replace=x_replace_inference,
        )
        return _response(run)
    except ModelInferenceError as exc:
        _raise(exc)
    finally:
        target.unlink(missing_ok=True)


@router.get("/model-inference/{run_id}", response_model=ModelInferenceResponse)
def get_inference(
    run_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> ModelInferenceResponse:
    try:
        return _response(service(request).get(user, run_id))
    except ModelInferenceError as exc:
        _raise(exc)


@router.post("/model-inference/{run_id}/keepalive", response_model=ModelInferenceResponse)
def keepalive(
    run_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> ModelInferenceResponse:
    require_same_origin(request)
    try:
        return _response(service(request).touch(user, run_id))
    except ModelInferenceError as exc:
        _raise(exc)


@router.post("/model-inference/{run_id}/save", response_model=ModelInferenceResponse)
def save_inference(
    run_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> ModelInferenceResponse:
    require_same_origin(request)
    try:
        return _response(service(request).save(user, run_id))
    except ModelInferenceError as exc:
        _raise(exc)


@router.delete("/model-inference/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inference(
    run_id: str, request: Request, user: Annotated[User, Depends(current_user)]
) -> Response:
    require_same_origin(request)
    try:
        service(request).delete(user, run_id)
    except ModelInferenceError as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/model-inference/{run_id}/files/{kind}")
def inference_file(
    run_id: str,
    kind: Literal["source", "preview", "result"],
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FileResponse:
    try:
        file_kind = "source" if kind == "preview" else kind
        path, name = service(request).file(user, run_id, file_kind)
        if kind == "preview" and path.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            preview = path.parent / "source-preview.mp4"
            if preview.is_file():
                path, name = preview, preview.name
        return FileResponse(path, filename=name if kind != "preview" else None)
    except ModelInferenceError as exc:
        _raise(exc)
