from fastapi import FastAPI

from .api.annotations import router as annotations_router
from .api.auth import router as auth_router
from .api.capabilities import router as capabilities_router
from .api.filesystem import router as filesystem_router
from .api.labels import router as labels_router
from .api.media import global_task_router, router as media_router
from .api.projects import router as projects_router
from .api.registrations import router as registrations_router
from .api.sampling import router as sampling_router
from .api.setup import router as setup_router
from .capabilities import SystemCapabilities, detect_capabilities
from .config import RuntimeSettings
from .services.auth import build_auth_service
from .services.annotations import AnnotationService
from .services.media import MediaService
from .services.labels import LabelService
from .services.projects import ProjectService
from .services.sampling import SamplingService
from .services.setup import SetupService
from .setup.tokens import SetupToken
from .storage.locator import WorkspaceLocator, default_locator_path


def create_app(
    settings: RuntimeSettings | None = None,
    setup_token: SetupToken | None = None,
    locator: WorkspaceLocator | None = None,
    capabilities: SystemCapabilities | None = None,
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
    app.state.capabilities = capabilities or detect_capabilities()
    app.state.settings = resolved_settings
    app.state.workspace = workspace
    auth_service = (
        build_auth_service(workspace, resolved_settings) if workspace is not None else None
    )
    app.state.auth_service = auth_service
    app.state.project_service = (
        ProjectService(auth_service.engine, resolved_settings, workspace)
        if auth_service is not None and workspace is not None
        else None
    )
    app.state.label_service = (
        LabelService(auth_service.engine, app.state.project_service)
        if auth_service is not None and app.state.project_service is not None
        else None
    )
    app.state.annotation_service = (
        AnnotationService(auth_service.engine, app.state.project_service)
        if auth_service is not None and app.state.project_service is not None
        else None
    )
    app.state.media_service = (
        MediaService(auth_service.engine, resolved_settings, workspace)
        if auth_service is not None and workspace is not None
        else None
    )
    app.state.sampling_service = (
        SamplingService(auth_service.engine, resolved_settings, workspace)
        if auth_service is not None and workspace is not None
        else None
    )
    app.state.setup_token = token
    app.state.setup_service = SetupService(resolved_settings.home, resolved_locator, token)
    app.include_router(setup_router)
    app.include_router(auth_router)
    app.include_router(capabilities_router)
    app.include_router(filesystem_router)
    app.include_router(registrations_router)
    app.include_router(projects_router)
    app.include_router(labels_router)
    app.include_router(annotations_router)
    app.include_router(global_task_router)
    app.include_router(media_router)
    app.include_router(sampling_router)

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()

if app.state.workspace is None:
    print(f"Vision Dataset Workbench setup token: {app.state.setup_token.plaintext}")
