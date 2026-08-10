from datetime import datetime, timezone
from typing import Annotated, Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ..models import User
from ..services.projects import (
    InvalidProjectMember,
    MemberView,
    ProjectConflict,
    ProjectForbidden,
    ProjectNotFound,
    ProjectService,
    ProjectView,
)
from .auth import current_user, require_same_origin

router = APIRouter(prefix="/api/v1/projects", tags=["projects"])


class CreateProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=2000)


class UpdateProjectRequest(CreateProjectRequest):
    version: int = Field(ge=1)


class AddMemberRequest(BaseModel):
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,64}$")
    role: Literal["editor", "viewer"]


class ChangeMemberRequest(BaseModel):
    role: Literal["editor", "viewer"]


class ProjectResponse(BaseModel):
    id: str
    name: str
    description: str
    creator_id: str
    creator_username: str
    role: Literal["owner", "editor", "viewer"]
    version: int
    created_at: str
    updated_at: str


class ProjectPageResponse(BaseModel):
    items: list[ProjectResponse]
    page: int
    page_size: int
    total: int


class MemberResponse(BaseModel):
    id: str
    username: str
    status: str
    role: Literal["owner", "editor", "viewer"]
    created_at: str


def project_service(request: Request) -> ProjectService:
    service = request.app.state.project_service
    if service is None:
        raise HTTPException(status_code=503, detail="workspace is not initialized")
    return service


def _utc_text(value: datetime) -> str:
    if value.tzinfo is not None:
        value = value.astimezone(timezone.utc).replace(tzinfo=None)
    return f"{value.isoformat(timespec='seconds')}Z"


def _project_response(view: ProjectView) -> ProjectResponse:
    project = view.project
    return ProjectResponse(
        id=project.id,
        name=project.name,
        description=project.description,
        creator_id=project.creator_id,
        creator_username=view.creator_username,
        role=view.role,
        version=project.version,
        created_at=_utc_text(project.created_at),
        updated_at=_utc_text(project.updated_at),
    )


def _member_response(view: MemberView) -> MemberResponse:
    return MemberResponse(
        id=view.user.id,
        username=view.user.username,
        status=view.user.status,
        role=view.role,
        created_at=_utc_text(view.created_at),
    )


def _raise_http_error(exc: ValueError) -> NoReturn:
    if isinstance(exc, ProjectNotFound):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ProjectForbidden):
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    if isinstance(exc, ProjectConflict):
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("", response_model=ProjectPageResponse)
def list_projects(
    request: Request,
    user: Annotated[User, Depends(current_user)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 50,
) -> ProjectPageResponse:
    items, total = project_service(request).list_projects(
        user, page=page, page_size=page_size
    )
    return ProjectPageResponse(
        items=[_project_response(item) for item in items],
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(
    payload: CreateProjectRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> ProjectResponse:
    require_same_origin(request)
    try:
        view = project_service(request).create_project(
            user, payload.name, payload.description
        )
    except ValueError as exc:
        _raise_http_error(exc)
    return _project_response(view)


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> ProjectResponse:
    try:
        view = project_service(request).get_project(user, project_id)
    except ValueError as exc:
        _raise_http_error(exc)
    return _project_response(view)


@router.patch("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: str,
    payload: UpdateProjectRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> ProjectResponse:
    require_same_origin(request)
    try:
        view = project_service(request).update_project(
            user,
            project_id,
            payload.name,
            payload.description,
            version=payload.version,
        )
    except ValueError as exc:
        _raise_http_error(exc)
    return _project_response(view)


@router.delete("/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> None:
    require_same_origin(request)
    try:
        project_service(request).delete_project(user, project_id)
    except (ProjectNotFound, ProjectForbidden, ProjectConflict) as exc:
        _raise_http_error(exc)


@router.get("/{project_id}/members", response_model=list[MemberResponse])
def list_members(
    project_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> list[MemberResponse]:
    try:
        members = project_service(request).list_members(user, project_id)
    except ValueError as exc:
        _raise_http_error(exc)
    return [_member_response(member) for member in members]


@router.post(
    "/{project_id}/members",
    response_model=MemberResponse,
    status_code=status.HTTP_201_CREATED,
)
def add_member(
    project_id: str,
    payload: AddMemberRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> MemberResponse:
    require_same_origin(request)
    try:
        member = project_service(request).add_member(
            user, project_id, payload.username, payload.role
        )
    except (InvalidProjectMember, ProjectNotFound, ProjectForbidden, ProjectConflict) as exc:
        _raise_http_error(exc)
    return _member_response(member)


@router.patch("/{project_id}/members/{user_id}", response_model=MemberResponse)
def change_member(
    project_id: str,
    user_id: str,
    payload: ChangeMemberRequest,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> MemberResponse:
    require_same_origin(request)
    try:
        member = project_service(request).change_member_role(
            user, project_id, user_id, payload.role
        )
    except (InvalidProjectMember, ProjectNotFound, ProjectForbidden) as exc:
        _raise_http_error(exc)
    return _member_response(member)


@router.delete("/{project_id}/members/{user_id}", status_code=204)
def remove_member(
    project_id: str,
    user_id: str,
    request: Request,
    user: Annotated[User, Depends(current_user)],
) -> None:
    require_same_origin(request)
    try:
        project_service(request).remove_member(user, project_id, user_id)
    except (InvalidProjectMember, ProjectNotFound, ProjectForbidden) as exc:
        _raise_http_error(exc)
