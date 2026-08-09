from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field

from ..models import User
from ..storage.browser import (
    create_home_directory,
    list_home_entries,
    normalize_extensions,
)
from ..storage.paths import HomePathResolver, UnsafePathError
from .auth import current_user, require_same_origin

router = APIRouter(prefix="/api/v1/filesystem", tags=["filesystem"])


class CreateDirectoryRequest(BaseModel):
    parent: str = "."
    name: str = Field(min_length=1, max_length=128)


@router.get("")
def list_entries(
    request: Request,
    _user: Annotated[User, Depends(current_user)],
    path: str = ".",
    extensions: Annotated[list[str] | None, Query()] = None,
    search: Annotated[str, Query(max_length=128)] = "",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 100,
) -> dict[str, object]:
    resolver = HomePathResolver(request.app.state.settings.home)
    try:
        allowed_extensions = normalize_extensions(extensions or [])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        return list_home_entries(
            resolver,
            path,
            page=page,
            page_size=page_size,
            hidden_root=request.app.state.workspace,
            extensions=allowed_extensions,
            search=search,
        )
    except (OSError, UnsafePathError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/directories", status_code=status.HTTP_201_CREATED)
def create_directory(
    payload: CreateDirectoryRequest,
    request: Request,
    _user: Annotated[User, Depends(current_user)],
) -> dict[str, str]:
    require_same_origin(request)
    resolver = HomePathResolver(request.app.state.settings.home)
    try:
        return create_home_directory(resolver, payload.parent, payload.name)
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="directory already exists") from exc
    except (OSError, UnsafePathError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
