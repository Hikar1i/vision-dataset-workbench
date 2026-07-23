from fastapi import FastAPI

from .api.auth import router as auth_router
from .api.registrations import router as registrations_router
from .api.setup import router as setup_router
from .config import RuntimeSettings
from .services.auth import build_auth_service
from .services.setup import SetupService
from .setup.tokens import SetupToken
from .storage.locator import WorkspaceLocator, default_locator_path


def create_app(
    settings: RuntimeSettings | None = None,
    setup_token: SetupToken | None = None,
    locator: WorkspaceLocator | None = None,
) -> FastAPI:
    resolved_settings = settings or RuntimeSettings.from_env()
    resolved_locator = locator or WorkspaceLocator(default_locator_path(resolved_settings.home))
    candidate = resolved_settings.workspace or resolved_locator.read()
    workspace = (
        candidate
        if candidate is not None
        and candidate.is_relative_to(resolved_settings.home)
        and (candidate / "db" / "workbench.sqlite3").is_file()
        else None
    )
    token = setup_token or SetupToken.create()

    app = FastAPI(title="Vision Dataset Workbench", version="0.1.0")
    app.state.settings = resolved_settings
    app.state.workspace = workspace
    app.state.auth_service = (
        build_auth_service(workspace, resolved_settings) if workspace is not None else None
    )
    app.state.setup_token = token
    app.state.setup_service = SetupService(resolved_settings.home, resolved_locator, token)
    app.include_router(setup_router)
    app.include_router(auth_router)
    app.include_router(registrations_router)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

if app.state.workspace is None:
    print(f"Vision Dataset Workbench setup token: {app.state.setup_token.plaintext}")
