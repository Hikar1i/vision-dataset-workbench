import json
from datetime import datetime, timezone
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from ..models import InferenceModel, ModelProject, User
from ..services.models import (
    InvalidModel,
    ModelConflict,
    ModelForbidden,
    ModelNotFound,
    ModelService,
)
from .auth import current_user, require_same_origin
from .media import TaskResponse, _task_response

router = APIRouter(prefix="/api/v1", tags=["models"])


class CreateModelProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    series_type: Literal["archive"] = "archive"
    tags: list[str] = Field(default_factory=lambda: ["未分类"], min_length=1, max_length=20)


class UpdateModelProjectRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    version: int = Field(ge=1)
    tags: list[str] | None = Field(default=None, min_length=1, max_length=20)


class RegisterModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    source_path: str = Field(min_length=1, max_length=2048)


class UpdateModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    version: int = Field(ge=1)
    model_project_id: str | None = None


class ModelProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    series_type: Literal["archive", "training"]
    system_key: str | None
    created_by_id: str | None
    version: int
    can_manage: bool
    created_at: str
    updated_at: str
    tags: list[str]


class InferenceModelResponse(BaseModel):
    id: str
    model_project_id: str
    model_code: str
    name: str
    description: str
    parameters: dict[str, object]
    kind: Literal["yolo"]
    status: Literal["copying", "ready", "failed"]
    storage_path: str | None
    file_size: int | None
    sha256: str | None
    source_name: str
    error: str | None
    version: int
    can_manage: bool
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


def _project_response(
    service: ModelService, actor: User, project: ModelProject
) -> ModelProjectResponse:
    return ModelProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        series_type=project.series_type,
        system_key=project.system_key,
        created_by_id=project.created_by_id,
        version=project.version,
        can_manage=service.can_manage(actor, project),
        created_at=_utc_text(project.created_at),
        updated_at=_utc_text(project.updated_at),
        tags=service.project_tags(project.id),
    )


def _model_response(
    service: ModelService, actor: User, model: InferenceModel
) -> InferenceModelResponse:
    project = service.get_project(actor, model.model_project_id)
    try:
        parameters = json.loads(model.parameters)
    except (TypeError, ValueError):
        parameters = {}
    return InferenceModelResponse(
        id=model.id,
        model_project_id=model.model_project_id,
        model_code=model.model_code,
        name=model.name,
        description=model.description,
        parameters=parameters,
        kind=model.kind,
        status=model.status,
        storage_path=model.storage_path,
        file_size=model.file_size,
        sha256=model.sha256,
        source_name=model.source_name,
        error=model.error,
        version=model.version,
        can_manage=(service.can_manage(actor, project) and project.series_type == "archive"),
        created_at=_utc_text(model.created_at),
        updated_at=_utc_text(model.updated_at),
    )


def _raise_model_error(exc: ValueError) -> NoReturn:
    if isinstance(exc, ModelNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ModelForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ModelConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/models", response_model=list[InferenceModelResponse])
def list_models(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[InferenceModelResponse]:
    service = model_service(request)
    return [_model_response(service, user, item) for item in service.list_models(user)]


@router.get("/models/{model_id}", response_model=InferenceModelResponse)
def get_model(
    model_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> InferenceModelResponse:
    service = model_service(request)
    try:
        model = service.get_model(user, model_id)
    except ModelNotFound as exc:
        _raise_model_error(exc)
    return _model_response(service, user, model)


@router.get("/models/{model_id}/download")
def download_model(
    model_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> FileResponse:
    try:
        model, path = model_service(request).ready_model(model_id)
    except (ModelNotFound, InvalidModel) as exc:
        _raise_model_error(exc)
    return FileResponse(path, filename=f"{model.model_code}.pt", media_type="application/octet-stream")


@router.patch("/models/{model_id}", response_model=InferenceModelResponse)
def update_model(
    model_id: str,
    payload: UpdateModelRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> InferenceModelResponse:
    require_same_origin(request)
    service = model_service(request)
    try:
        model = service.update_model(user, model_id, **payload.model_dump())
    except (ModelNotFound, ModelForbidden, ModelConflict, InvalidModel) as exc:
        _raise_model_error(exc)
    return _model_response(service, user, model)


@router.delete("/models/{model_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model(
    model_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    require_same_origin(request)
    try:
        model_service(request).delete_model(user, model_id)
    except (ModelNotFound, ModelForbidden, ModelConflict) as exc:
        _raise_model_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/model-projects", response_model=list[ModelProjectResponse])
def list_model_projects(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[ModelProjectResponse]:
    service = model_service(request)
    return [_project_response(service, user, item) for item in service.list_projects(user)]


@router.post(
    "/model-projects",
    response_model=ModelProjectResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_model_project(
    payload: CreateModelProjectRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> ModelProjectResponse:
    require_same_origin(request)
    service = model_service(request)
    try:
        project = service.create_project(user, payload.name, payload.description, payload.tags)
    except (ModelConflict, InvalidModel) as exc:
        _raise_model_error(exc)
    return _project_response(service, user, project)


@router.get("/model-project-tags", response_model=list[str])
def list_model_project_tags(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[str]:
    return [tag.name for tag in model_service(request).list_tags()]


@router.get("/model-projects/{project_id}", response_model=ModelProjectResponse)
def get_model_project(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> ModelProjectResponse:
    service = model_service(request)
    try:
        project = service.get_project(user, project_id)
    except ModelNotFound as exc:
        _raise_model_error(exc)
    return _project_response(service, user, project)


@router.patch("/model-projects/{project_id}", response_model=ModelProjectResponse)
def update_model_project(
    project_id: str,
    payload: UpdateModelProjectRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> ModelProjectResponse:
    require_same_origin(request)
    service = model_service(request)
    try:
        project = service.update_project(user, project_id, **payload.model_dump())
    except (ModelNotFound, ModelForbidden, ModelConflict, InvalidModel) as exc:
        _raise_model_error(exc)
    return _project_response(service, user, project)


@router.delete("/model-projects/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_model_project(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    require_same_origin(request)
    try:
        model_service(request).delete_project(user, project_id)
    except (ModelNotFound, ModelForbidden, ModelConflict) as exc:
        _raise_model_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/model-projects/{project_id}/models", response_model=list[InferenceModelResponse])
def list_project_models(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[InferenceModelResponse]:
    service = model_service(request)
    try:
        items = service.list_project_models(user, project_id)
    except ModelNotFound as exc:
        _raise_model_error(exc)
    return [_model_response(service, user, item) for item in items]


@router.post(
    "/model-projects/{project_id}/models",
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
    service = model_service(request)
    try:
        registered = service.register(
            user,
            project_id,
            payload.name,
            payload.source_path,
            payload.description,
        )
    except (ModelNotFound, ModelForbidden, InvalidModel) as exc:
        _raise_model_error(exc)
    return RegisteredModelResponse(
        model=_model_response(service, user, registered.model),
        task=_task_response(registered.task),
    )
