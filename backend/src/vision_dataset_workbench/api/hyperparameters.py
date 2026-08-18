import json
from datetime import datetime, timezone
from typing import Annotated, Any, Literal, NoReturn

import yaml
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from ..models import HyperparameterTemplate, User
from ..services.hyperparameters import (
    HyperparameterTemplateService,
    InvalidTemplate,
    TemplateConflict,
    TemplateForbidden,
    TemplateNotFound,
)
from ..training.hyperparameters import (
    HyperparameterValidationError,
    catalog_payload,
    effective_parameters,
    parse_raw,
)
from .auth import current_user, require_same_origin

router = APIRouter(prefix="/api/v1", tags=["hyperparameters"])


class CreateTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    epochs: int
    batch_mode: Literal["auto", "fixed", "fraction"]
    batch_value: float | None = None
    image_size: int
    extra_parameters: dict[str, object] = Field(default_factory=dict)
    derived_from_id: str | None = None


class UpdateTemplateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    epochs: int
    batch_mode: Literal["auto", "fixed", "fraction"]
    batch_value: float | None = None
    image_size: int
    extra_parameters: dict[str, object] = Field(default_factory=dict)


class RawRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    raw: str = Field(max_length=100_000)


class ValidationIssueResponse(BaseModel):
    code: str
    message: str
    key: str | None
    line: int | None
    column: int | None


class RawValidationResponse(BaseModel):
    valid: bool
    normalized: dict[str, object] | None = None
    normalized_raw: str | None = None
    issues: list[ValidationIssueResponse] = Field(default_factory=list)


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    epochs: int
    batch_mode: Literal["auto", "fixed", "fraction"]
    batch_value: float | None
    image_size: int
    extra_parameters: dict[str, object]
    effective_parameters: dict[str, object]
    catalog_version: str
    system_key: str | None
    derived_from_id: str | None
    created_by_id: str | None
    can_manage: bool
    can_edit: bool
    version: int
    created_at: str
    updated_at: str


def service(request: Request) -> HyperparameterTemplateService:
    value = request.app.state.hyperparameter_template_service
    if value is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return value


def _time(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def _response(
    svc: HyperparameterTemplateService, actor: User, item: HyperparameterTemplate
) -> TemplateResponse:
    extra = json.loads(item.extra_parameters)
    return TemplateResponse(
        id=item.id,
        name=item.name,
        description=item.description,
        epochs=item.epochs,
        batch_mode=item.batch_mode,
        batch_value=item.batch_value,
        image_size=item.image_size,
        extra_parameters=extra,
        effective_parameters=effective_parameters(
            item.epochs, item.batch_mode, item.batch_value, item.image_size, extra
        ),
        catalog_version=item.catalog_version,
        system_key=item.system_key,
        derived_from_id=item.derived_from_id,
        created_by_id=item.created_by_id,
        can_manage=svc.can_manage(actor, item),
        can_edit=svc.can_manage(actor, item),
        version=item.version,
        created_at=_time(item.created_at),
        updated_at=_time(item.updated_at),
    )


def _raise(exc: ValueError) -> NoReturn:
    if isinstance(exc, TemplateNotFound):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, TemplateForbidden):
        raise HTTPException(403, str(exc)) from exc
    if isinstance(exc, TemplateConflict):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(exc, HyperparameterValidationError):
        raise HTTPException(422, [issue.__dict__ for issue in exc.issues]) from exc
    raise HTTPException(422, str(exc)) from exc


@router.get("/hyperparameter-catalog", response_model=dict[str, Any])
def get_catalog(user: Annotated[User, Depends(current_user)]) -> dict[str, Any]:
    return catalog_payload()


@router.post("/hyperparameter-templates/validate-raw", response_model=RawValidationResponse)
def validate_raw(
    payload: RawRequest,
    user: Annotated[User, Depends(current_user)],
) -> RawValidationResponse:
    try:
        normalized = parse_raw(payload.raw)
    except HyperparameterValidationError as exc:
        return RawValidationResponse(
            valid=False,
            issues=[ValidationIssueResponse(**issue.__dict__) for issue in exc.issues],
        )
    values = effective_parameters(
        normalized["epochs"],
        normalized["batch_mode"],
        normalized["batch_value"],
        normalized["image_size"],
        normalized["extra_parameters"],
    )
    return RawValidationResponse(
        valid=True,
        normalized=normalized,
        normalized_raw=yaml.safe_dump(values, allow_unicode=True, sort_keys=False),
    )


@router.get("/hyperparameter-templates", response_model=list[TemplateResponse])
def list_templates(
    request: Request, user: Annotated[User, Depends(current_user)]
) -> list[TemplateResponse]:
    svc = service(request)
    return [_response(svc, user, item) for item in svc.list(user)]


@router.post(
    "/hyperparameter-templates",
    response_model=TemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_template(
    payload: CreateTemplateRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> TemplateResponse:
    require_same_origin(request)
    svc = service(request)
    try:
        item = svc.create(user, **payload.model_dump())
    except (
        InvalidTemplate,
        TemplateNotFound,
        TemplateConflict,
        HyperparameterValidationError,
    ) as exc:
        _raise(exc)
    return _response(svc, user, item)


@router.get("/hyperparameter-templates/{template_id}", response_model=TemplateResponse)
def get_template(
    template_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> TemplateResponse:
    svc = service(request)
    try:
        item = svc.get(user, template_id)
    except TemplateNotFound as exc:
        _raise(exc)
    return _response(svc, user, item)


@router.patch("/hyperparameter-templates/{template_id}", response_model=TemplateResponse)
def update_template(
    template_id: str,
    payload: UpdateTemplateRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> TemplateResponse:
    require_same_origin(request)
    svc = service(request)
    try:
        item = svc.update(user, template_id, **payload.model_dump())
    except (
        InvalidTemplate,
        TemplateNotFound,
        TemplateForbidden,
        TemplateConflict,
        HyperparameterValidationError,
    ) as exc:
        _raise(exc)
    return _response(svc, user, item)


@router.delete("/hyperparameter-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(
    template_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> Response:
    require_same_origin(request)
    try:
        service(request).delete(user, template_id)
    except (TemplateNotFound, TemplateForbidden) as exc:
        _raise(exc)
    return Response(status_code=204)
