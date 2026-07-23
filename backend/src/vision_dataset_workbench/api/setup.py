from fastapi import APIRouter, Header, HTTPException, Request, status
from pydantic import BaseModel, Field

from ..services.auth import build_auth_service
from ..services.setup import SetupConflict, SetupService
from ..setup.tokens import InvalidSetupToken
from ..storage.paths import HomePathResolver, UnsafePathError

router = APIRouter(prefix="/api/v1/setup", tags=["setup"])


class CreateDirectoryRequest(BaseModel):
    parent: str = "."
    name: str = Field(min_length=1, max_length=128)


class InitializeRequest(BaseModel):
    parent: str
    username: str = Field(pattern=r"^[A-Za-z0-9_.-]{3,64}$")
    password: str = Field(min_length=12, max_length=256)


def require_token(request: Request, candidate: str | None) -> None:
    try:
        request.app.state.setup_token.verify(candidate or "")
    except InvalidSetupToken as exc:
        raise HTTPException(status_code=403, detail="invalid setup token") from exc


@router.get("/status")
def setup_status(request: Request) -> dict[str, bool]:
    return {"initialized": request.app.state.workspace is not None}


@router.get("/directories")
def list_directories(
    request: Request,
    path: str = ".",
    page: int = 1,
    page_size: int = 100,
    x_setup_token: str | None = Header(default=None),
) -> dict[str, object]:
    require_token(request, x_setup_token)
    if page < 1 or page_size < 1 or page_size > 200:
        raise HTTPException(status_code=422, detail="invalid pagination")

    resolver = HomePathResolver(request.app.state.settings.home)
    try:
        directory = resolver.resolve_existing(path)
        hidden_workspace = request.app.state.workspace
        children = sorted(
            (
                item
                for item in directory.iterdir()
                if item.is_dir()
                and item.resolve().is_relative_to(resolver.home)
                and (hidden_workspace is None or item.resolve() != hidden_workspace)
            ),
            key=lambda item: item.name.casefold(),
        )
    except (OSError, UnsafePathError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    start = (page - 1) * page_size
    items = [
        {"name": child.name, "path": child.relative_to(resolver.home).as_posix()}
        for child in children[start : start + page_size]
    ]
    parent = (
        None
        if directory == resolver.home
        else directory.parent.relative_to(resolver.home).as_posix()
    )
    return {
        "path": resolver.display(directory),
        "parent": parent,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": len(children),
    }


@router.post("/directories", status_code=status.HTTP_201_CREATED)
def create_directory(
    payload: CreateDirectoryRequest,
    request: Request,
    x_setup_token: str | None = Header(default=None),
) -> dict[str, str]:
    require_token(request, x_setup_token)
    resolver = HomePathResolver(request.app.state.settings.home)
    try:
        target = resolver.resolve_child(payload.parent, payload.name)
        target.mkdir()
    except FileExistsError as exc:
        raise HTTPException(status_code=409, detail="directory already exists") from exc
    except (OSError, UnsafePathError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "path": target.relative_to(resolver.home).as_posix(),
        "display_path": resolver.display(target),
    }


@router.post("/initialize", status_code=status.HTTP_201_CREATED)
def initialize(
    payload: InitializeRequest,
    request: Request,
    x_setup_token: str | None = Header(default=None),
) -> dict[str, object]:
    require_token(request, x_setup_token)
    service: SetupService = request.app.state.setup_service
    try:
        workspace = service.initialize(
            x_setup_token or "", payload.parent, payload.username, payload.password
        )
    except InvalidSetupToken as exc:
        raise HTTPException(status_code=403, detail="invalid setup token") from exc
    except SetupConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except (OSError, UnsafePathError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    request.app.state.workspace = workspace
    request.app.state.auth_service = build_auth_service(
        workspace, request.app.state.settings
    )
    return {"initialized": True, "workspace": ".vision-dataset-workbench"}
