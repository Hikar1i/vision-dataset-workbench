import json
from datetime import datetime, timezone
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ..models import ModelArtifact, User
from ..services.model_artifacts import (
    InvalidModelArtifact,
    ModelArtifactConflict,
    ModelArtifactForbidden,
    ModelArtifactNotFound,
    ModelArtifactService,
)
from .auth import current_user, require_same_origin
from .media import TaskResponse, _task_response

router = APIRouter(prefix="/api/v1", tags=["model-artifacts"])


class CreateModelArtifactRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["onnx", "engine"]
    image_size: int = Field(default=640, ge=32, le=8192, multiple_of=32)
    dynamic: bool = False
    precision: Literal["fp16", "fp32"] = "fp16"


class ModelArtifactResponse(BaseModel):
    id: str
    model_id: str
    format: Literal["onnx", "engine"]
    status: Literal["queued", "converting", "ready", "failed", "stale"]
    source_model_sha256: str
    export_config: dict[str, object]
    file_size: int | None
    sha256: str | None
    gpu_uuid: str | None
    gpu_index: int | None
    task_id: str | None
    error: str | None
    created_at: str
    updated_at: str
    completed_at: str | None


class CreatedModelArtifactResponse(BaseModel):
    artifact: ModelArtifactResponse
    task: TaskResponse


def model_artifact_service(request: Request) -> ModelArtifactService:
    service = request.app.state.model_artifact_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def _utc_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def _response(artifact: ModelArtifact) -> ModelArtifactResponse:
    return ModelArtifactResponse(
        id=artifact.id,
        model_id=artifact.model_id,
        format=artifact.format,
        status=artifact.status,
        source_model_sha256=artifact.source_model_sha256,
        export_config=json.loads(artifact.export_config),
        file_size=artifact.file_size,
        sha256=artifact.sha256,
        gpu_uuid=artifact.gpu_uuid,
        gpu_index=artifact.gpu_index,
        task_id=artifact.task_id,
        error=artifact.error,
        created_at=_utc_text(artifact.created_at) or "",
        updated_at=_utc_text(artifact.updated_at) or "",
        completed_at=_utc_text(artifact.completed_at),
    )


def _raise(exc: ValueError) -> NoReturn:
    if isinstance(exc, ModelArtifactNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ModelArtifactForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ModelArtifactConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/models/{model_id}/artifacts", response_model=list[ModelArtifactResponse])
def list_model_artifacts(
    model_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[ModelArtifactResponse]:
    try:
        return [_response(item) for item in model_artifact_service(request).list(user, model_id)]
    except (ModelArtifactNotFound, InvalidModelArtifact) as exc:
        _raise(exc)


@router.post(
    "/models/{model_id}/artifacts",
    response_model=CreatedModelArtifactResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def create_model_artifact(
    model_id: str,
    payload: CreateModelArtifactRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> CreatedModelArtifactResponse:
    require_same_origin(request)
    try:
        artifact, task = model_artifact_service(request).create(
            user,
            model_id,
            payload.format,
            image_size=payload.image_size,
            dynamic=payload.dynamic,
            precision=payload.precision,
        )
    except (
        ModelArtifactNotFound,
        ModelArtifactForbidden,
        ModelArtifactConflict,
        InvalidModelArtifact,
    ) as exc:
        _raise(exc)
    return CreatedModelArtifactResponse(artifact=_response(artifact), task=_task_response(task))


@router.get("/model-artifacts/{artifact_id}/download")
def download_model_artifact(
    artifact_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FileResponse:
    try:
        artifact, path, model_code = model_artifact_service(request).downloadable(
            user, artifact_id
        )
    except (ModelArtifactNotFound, ModelArtifactConflict) as exc:
        _raise(exc)
    suffix = "onnx" if artifact.format == "onnx" else "engine"
    headers = (
        {"X-VDW-TensorRT-Compatibility": "current-server-only"}
        if artifact.format == "engine"
        else None
    )
    return FileResponse(
        path,
        filename=f"{model_code}-{artifact.format}-{artifact.id[:8]}.{suffix}",
        media_type="application/octet-stream",
        headers=headers,
    )


@router.delete("/model-artifacts/{artifact_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_artifact(
    artifact_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    require_same_origin(request)
    try:
        model_artifact_service(request).delete(user, artifact_id)
    except (
        ModelArtifactNotFound,
        ModelArtifactForbidden,
        ModelArtifactConflict,
    ) as exc:
        _raise(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
