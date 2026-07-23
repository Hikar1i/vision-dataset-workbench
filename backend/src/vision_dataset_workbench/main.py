from fastapi import FastAPI

from .config import RuntimeSettings


def create_app(settings: RuntimeSettings | None = None) -> FastAPI:
    app = FastAPI(title="Vision Dataset Workbench", version="0.1.0")
    app.state.settings = settings or RuntimeSettings.from_env()

    @app.get("/api/v1/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
