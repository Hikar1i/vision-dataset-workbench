from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from ..models import User
from ..security.credentials import CredentialEncryptionUnavailable
from ..services.xanylabeling_settings import (
    InvalidXAnyLabelingSetting,
    PublicXAnyLabelingSetting,
    XAnyLabelingSettingConflict,
    XAnyLabelingSettingsService,
    XAnyLabelingSettingUnavailable,
)
from ..xanylabeling import RemoteModelOption
from .auth import current_user, require_same_origin

router = APIRouter(prefix="/api/v1/me/x-anylabeling-server", tags=["models"])


class XAnyLabelingSettingResponse(BaseModel):
    configured: bool
    server_url: str
    has_api_key: bool
    available: bool


class RemoteModelResponse(BaseModel):
    key: str
    model_id: str
    task_id: str | None
    name: str
    batch_processing_mode: Literal["default", "text_prompt"]


class SaveXAnyLabelingSettingRequest(BaseModel):
    server_url: str = Field(min_length=1, max_length=2048)
    api_key_mode: Literal["retain", "replace", "clear"] = "retain"
    api_key: str | None = Field(default=None, max_length=4096)


class SavedXAnyLabelingSettingResponse(BaseModel):
    setting: XAnyLabelingSettingResponse
    models: list[RemoteModelResponse]


def settings_service(request: Request) -> XAnyLabelingSettingsService:
    service = request.app.state.xanylabeling_settings_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def _setting_response(
    setting: PublicXAnyLabelingSetting,
) -> XAnyLabelingSettingResponse:
    return XAnyLabelingSettingResponse(**setting.__dict__)


def _model_response(model: RemoteModelOption) -> RemoteModelResponse:
    return RemoteModelResponse(**model.__dict__)


def _raise_setting_error(exc: ValueError) -> NoReturn:
    if isinstance(exc, XAnyLabelingSettingConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    if isinstance(exc, InvalidXAnyLabelingSetting):
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if isinstance(
        exc, (XAnyLabelingSettingUnavailable, CredentialEncryptionUnavailable)
    ):
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=XAnyLabelingSettingResponse)
def get_setting(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> XAnyLabelingSettingResponse:
    return _setting_response(settings_service(request).get_public(user))


@router.put("", response_model=SavedXAnyLabelingSettingResponse)
def save_setting(
    payload: SaveXAnyLabelingSettingRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> SavedXAnyLabelingSettingResponse:
    require_same_origin(request)
    try:
        setting, models = settings_service(request).save_verified(
            user, payload.server_url, payload.api_key_mode, payload.api_key
        )
    except ValueError as exc:
        _raise_setting_error(exc)
    return SavedXAnyLabelingSettingResponse(
        setting=_setting_response(setting),
        models=[_model_response(model) for model in models],
    )


@router.get("/models", response_model=list[RemoteModelResponse])
def list_models(
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[RemoteModelResponse]:
    try:
        models = settings_service(request).list_models(user)
    except ValueError as exc:
        _raise_setting_error(exc)
    return [_model_response(model) for model in models]
