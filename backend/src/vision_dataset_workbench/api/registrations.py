from datetime import datetime, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ..models import User
from ..services.auth import (
    AuthConflict,
    AuthenticationFailed,
    AuthService,
    UserNotFound,
)
from .auth import auth_service, current_user, require_same_origin

router = APIRouter(tags=["users"])


class RegistrationRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.-]{2,63}$")
    password: str = Field(min_length=12, max_length=256)


class ManagedUserResponse(BaseModel):
    id: str
    username: str
    status: str
    is_system_admin: bool
    created_at: str
    reviewed_at: str | None


class UserPageResponse(BaseModel):
    items: list[ManagedUserResponse]
    page: int
    page_size: int
    total: int


def _utc_text(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def managed_user_response(user: User) -> ManagedUserResponse:
    return ManagedUserResponse(
        id=user.id,
        username=user.username,
        status=user.status,
        is_system_admin=user.is_system_admin,
        created_at=_utc_text(user.created_at) or "",
        reviewed_at=_utc_text(user.reviewed_at),
    )


def system_admin(user: Annotated[User, Depends(current_user)]) -> User:
    if not user.is_system_admin:
        raise HTTPException(status_code=403, detail="administrator access required")
    return user


@router.post(
    "/api/v1/registrations",
    response_model=ManagedUserResponse,
    status_code=status.HTTP_201_CREATED,
)
def register(payload: RegistrationRequest, request: Request) -> ManagedUserResponse:
    require_same_origin(request)
    try:
        user = auth_service(request).register(payload.username, payload.password)
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except AuthConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return managed_user_response(user)


@router.get("/api/v1/admin/users", response_model=UserPageResponse)
def list_users(
    request: Request,
    _administrator: Annotated[User, Depends(system_admin)],
    status_filter: Annotated[
        Literal["", "pending", "active", "rejected", "disabled"] | None,
        Query(alias="status"),
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


@router.post(
    "/api/v1/admin/users/{user_id}/{action}", response_model=ManagedUserResponse
)
def set_user_status(
    user_id: str,
    action: Literal["approve", "reject", "disable", "enable"],
    request: Request,
    administrator: Annotated[User, Depends(system_admin)],
) -> ManagedUserResponse:
    require_same_origin(request)
    service: AuthService = auth_service(request)
    try:
        user = service.set_user_status(user_id, action, administrator.id)
    except UserNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except AuthConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return managed_user_response(user)
