import json
from datetime import datetime, timezone
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..models import InferenceModel, ModelProject, User
from ..services.models import (
    InvalidModel,
    ModelForbidden,
    ModelNotFound,
    ModelService,
)
from ..services.projects import ProjectForbidden, ProjectNotFound
from .auth import current_user, require_same_origin
from .media import TaskResponse, _task_response

router = APIRouter(tags=["models"])


class RegisterModelRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    source_path: str = Field(min_length=1, max_length=2048)


class ModelProjectResponse(BaseModel):
    id: str
    name: str
    series_type: Literal["archive", "training"]
    system_key: str | None
    created_at: str


class InferenceModelResponse(BaseModel):
    id: str
    model_project_id: str
    name: str
    description: str
    parameters: dict[str, object]
    kind: Literal["yolo"]
    status: Literal["copying", "ready", "failed"]
    source_name: str
    error: str | None
    created_at: str
    updated_at: str


class RegisteredModelResponse(BaseModel):
    model: InferenceModelResponse
    task: TaskResponse


def model_service(request: Request) -> ModelService:
    service = request.app.state.model_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def _utc_text(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def _model_response(model: InferenceModel) -> InferenceModelResponse:
    return InferenceModelResponse(
        id=model.id,
        model_project_id=model.model_project_id,
        name=model.name,
        description=model.description,
        parameters=json.loads(model.parameters),
        kind=model.kind,
        status=model.status,
        source_name=model.source_name,
        error=model.error,
        created_at=_utc_text(model.created_at),
        updated_at=_utc_text(model.updated_at),
    )


def _project_response(project: ModelProject) -> ModelProjectResponse:
    return ModelProjectResponse(
        id=project.id,
        name=project.name,
        series_type=project.series_type,
        system_key=project.system_key,
        created_at=_utc_text(project.created_at),
    )


def _raise_model_error(exc: ValueError) -> NoReturn:
    if isinstance(exc, (ProjectNotFound, ModelNotFound)):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, (ProjectForbidden, ModelForbidden)):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/api/v1/models", response_model=list[InferenceModelResponse])
def list_models(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[InferenceModelResponse]:
    return [_model_response(item) for item in model_service(request).list_models(user)]


@router.get("/api/v1/model-projects", response_model=list[ModelProjectResponse])
def list_model_projects(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[ModelProjectResponse]:
    return [_project_response(item) for item in model_service(request).list_projects(user)]


@router.get(
    "/api/v1/model-projects/{model_project_id}/models",
    response_model=list[InferenceModelResponse],
)
def list_project_models(
    model_project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[InferenceModelResponse]:
    try:
        items = model_service(request).list_project_models(user, model_project_id)
    except ModelNotFound as exc:
        _raise_model_error(exc)
    return [_model_response(item) for item in items]


@router.post(
    "/api/v1/projects/{project_id}/models",
    response_model=RegisteredModelResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def register_model(
    project_id: str,
    payload: RegisterModelRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> RegisteredModelResponse:
    require_same_origin(request)
    try:
        registered = model_service(request).register(
            user, project_id, payload.name, payload.source_path
        )
    except (
        ProjectNotFound,
        ProjectForbidden,
        ModelForbidden,
        InvalidModel,
    ) as exc:
        _raise_model_error(exc)
    return RegisteredModelResponse(
        model=_model_response(registered.model),
        task=_task_response(registered.task),
    )
