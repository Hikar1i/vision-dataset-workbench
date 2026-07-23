from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

from ..models import User
from ..services.auth import (
    ABSOLUTE_LIFETIME,
    COOKIE_NAME,
    AuthenticationFailed,
    AuthService,
)

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(min_length=12, max_length=256)


class UserResponse(BaseModel):
    id: str
    username: str
    status: str
    is_system_admin: bool


def auth_service(request: Request) -> AuthService:
    service = request.app.state.auth_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    expected = f"{request.url.scheme}://{request.headers.get('host')}"
    if origin != expected:
        raise HTTPException(status_code=403, detail="cross-origin request rejected")


def current_user(request: Request) -> User:
    token = request.cookies.get(COOKIE_NAME, "")
    try:
        return auth_service(request).authenticate(token)
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=401, detail="authentication required") from exc


def user_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        username=user.username,
        status=user.status,
        is_system_admin=user.is_system_admin,
    )


def set_session_cookie(response: Response, request: Request, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        max_age=int(ABSOLUTE_LIFETIME.total_seconds()),
        path="/",
    )


@router.get("/status")
def status(request: Request) -> dict[str, object]:
    settings = request.app.state.settings
    return {
        "mode": settings.app_mode,
        "registration_enabled": settings.registration_enabled,
    }


@router.post("/login", response_model=UserResponse)
def login(payload: LoginRequest, request: Request, response: Response) -> UserResponse:
    require_same_origin(request)
    try:
        created = auth_service(request).login(payload.username, payload.password)
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=401, detail="invalid username or password") from exc
    set_session_cookie(response, request, created.token)
    return user_response(created.user)


@router.get("/me", response_model=UserResponse)
def me(user: Annotated[User, Depends(current_user)]) -> UserResponse:
    return user_response(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response) -> None:
    require_same_origin(request)
    auth_service(request).logout(request.cookies.get(COOKIE_NAME, ""))
    response.delete_cookie(COOKIE_NAME, path="/")


@router.put("/password", response_model=UserResponse)
def change_password(
    payload: ChangePasswordRequest, request: Request, response: Response
) -> UserResponse:
    require_same_origin(request)
    try:
        created = auth_service(request).change_password(
            request.cookies.get(COOKIE_NAME, ""),
            payload.current_password,
            payload.new_password,
        )
    except AuthenticationFailed as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    set_session_cookie(response, request, created.token)
    return user_response(created.user)
