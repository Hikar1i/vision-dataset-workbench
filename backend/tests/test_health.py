from fastapi.testclient import TestClient

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.main import create_app


def test_health_returns_service_status(tmp_path):
    app = create_app(RuntimeSettings(home=tmp_path, workspace=None))
    response = TestClient(app).get("/api/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
