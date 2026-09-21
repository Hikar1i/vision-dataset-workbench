from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ..models import User
from ..services.auth import AuthConflict, UserNotFound
from .auth import auth_service, current_user, require_same_origin

router = APIRouter(prefix="/api/v1/admin/users", tags=["users"])


class CreateUserRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,64}$")


class ManagedUserResponse(BaseModel):
    id: str
    username: str
    status: str
    is_system_admin: bool
    must_change_password: bool
    created_at: str


class ProvisionedUserResponse(ManagedUserResponse):
    initial_password: str


class UserPageResponse(BaseModel):
    items: list[ManagedUserResponse]
    page: int
    page_size: int
    total: int


def _utc_text(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def managed_user_response(user: User) -> ManagedUserResponse:
    return ManagedUserResponse(
        id=user.id,
        username=user.username,
        status=user.status,
        is_system_admin=user.is_system_admin,
        must_change_password=user.must_change_password,
        created_at=_utc_text(user.created_at),
    )


def system_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_system_admin:
        raise HTTPException(status_code=403, detail="administrator access required")
    return user


@router.post("", response_model=ProvisionedUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    payload: CreateUserRequest,
    request: Request,
    _administrator: Annotated[User, Depends(system_admin)],
) -> ProvisionedUserResponse:
    require_same_origin(request)
    try:
        created = auth_service(request).create_user(payload.username)
    except (ValueError, AuthConflict) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ProvisionedUserResponse(
        **managed_user_response(created.user).model_dump(),
        initial_password=created.initial_password,
    )


@router.get("", response_model=UserPageResponse)
def list_users(
    request: Request,
    _administrator: Annotated[User, Depends(system_admin)],
    status_filter: Annotated[
        Literal["", "active", "disabled"] | None, Query(alias="status")
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> UserPageResponse:
    users, total = auth_service(request).list_users(
        status=status_filter, page=page, page_size=page_size
    )
    return UserPageResponse(
        items=[managed_user_response(user) for user in users],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/{user_id}/reset-password", response_model=ProvisionedUserResponse)
def reset_password(
    user_id: str,
    request: Request,
    _administrator: Annotated[User, Depends(system_admin)],
) -> ProvisionedUserResponse:
    require_same_origin(request)
    try:
        created = auth_service(request).reset_user_password(user_id)
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AuthConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return ProvisionedUserResponse(
        **managed_user_response(created.user).model_dump(),
        initial_password=created.initial_password,
    )


@router.post("/{user_id}/{action}", response_model=ManagedUserResponse)
def set_user_status(
    user_id: str,
    action: Literal["disable", "enable"],
    request: Request,
    _administrator: Annotated[User, Depends(system_admin)],
) -> ManagedUserResponse:
    require_same_origin(request)
    try:
        user = auth_service(request).set_user_status(user_id, action)
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AuthConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return managed_user_response(user)
