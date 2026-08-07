from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from ..models import User
from ..services.llm_configs import LLMConfigService
from .auth import current_user, require_same_origin

router = APIRouter(prefix="/api/v1/me/llm-configs", tags=["llm-configs"])


class LLMConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    name: str
    description: str
    base_url: str
    api_type: str
    model_name: str
    has_api_key: bool
    enabled: bool
    available: bool
    last_test_status: str
    last_test_latency_ms: int | None
    advanced_options: dict[str, object]
    version: int
    created_at: str
    updated_at: str


class LLMConfigPayload(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)
    base_url: str = Field(min_length=1, max_length=2048)
    api_type: str = Field(default="openai", pattern="^(openai|anthropic)$")
    model_name: str = Field(min_length=1, max_length=256)
    api_key: str | None = Field(default=None, max_length=4096)
    enabled: bool = True
    advanced_options: dict[str, object] = {}


class DefaultsPayload(BaseModel):
    options: dict[str, object]


def service(request: Request) -> LLMConfigService:
    value = request.app.state.llm_config_service
    if value is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return value


@router.get("", response_model=list[LLMConfigResponse])
def list_configs(request: Request, user: Annotated[User, Depends(current_user)]):
    return service(request).list(user)


@router.post("", response_model=LLMConfigResponse, status_code=status.HTTP_201_CREATED)
def create_config(payload: LLMConfigPayload, request: Request, user: Annotated[User, Depends(current_user)]):
    require_same_origin(request)
    try:
        return service(request).save(user, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/{config_id}", response_model=LLMConfigResponse)
def update_config(config_id: str, payload: LLMConfigPayload, request: Request, user: Annotated[User, Depends(current_user)]):
    require_same_origin(request)
    try:
        return service(request).save(user, payload.model_dump(), config_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_config(config_id: str, request: Request, user: Annotated[User, Depends(current_user)]):
    require_same_origin(request)
    try:
        service(request).delete(user, config_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{config_id}/test")
def test_config(config_id: str, request: Request, user: Annotated[User, Depends(current_user)]):
    require_same_origin(request)
    try:
        return service(request).test_connection(user, config_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/defaults")
def get_defaults(request: Request, user: Annotated[User, Depends(current_user)]):
    return service(request).defaults(user)


@router.put("/defaults")
def save_defaults(payload: DefaultsPayload, request: Request, user: Annotated[User, Depends(current_user)]):
    require_same_origin(request)
    return service(request).save_defaults(user, payload.options)
