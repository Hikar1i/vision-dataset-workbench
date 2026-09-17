from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.capabilities import (
    CapabilityStatus,
    FeatureCapabilities,
    GpuDevice,
    GpuStatus,
    SystemCapabilities,
)
from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import InferenceModel, ModelArtifact, Task, User
from vision_dataset_workbench.security.passwords import hash_password

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


def capabilities():
    yes = CapabilityStatus(True)
    return SystemCapabilities(
        gpu=GpuStatus(True, None, (GpuDevice(0, "A4000", 16000, "GPU-a", "8.6"),)),
        pytorch_cuda=yes,
        features=FeatureCapabilities(yes, yes, yes, yes, yes, yes),
    )


def client_for(app, username):
    client = TestClient(app)
    assert client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": username, "password": PASSWORD},
    ).status_code == 200
    return client


def setup_app(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    home.mkdir()
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    with Session(engine) as database:
        database.add_all(
            [
                User(
                    id="admin-id",
                    username="admin",
                    username_normalized="admin",
                    password_hash=hash_password(PASSWORD),
                    is_system_admin=True,
                ),
                User(
                    id="viewer-id",
                    username="viewer",
                    username_normalized="viewer",
                    password_hash=hash_password(PASSWORD),
                ),
            ]
        )
        database.commit()
    engine.dispose()
    app = create_app(
        RuntimeSettings(home=home, workspace=workspace), capabilities=capabilities()
    )
    admin, viewer = client_for(app, "admin"), client_for(app, "viewer")
    project = admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Models", "description": ""},
    ).json()
    source = workspace / "models" / "model-id" / "best.pt"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"weights")
    with app.state.model_service._session_factory() as database:
        database.add(
            InferenceModel(
                id="model-id",
                model_project_id=project["id"],
                name="Detector",
                model_code="detector",
                kind="yolo",
                status="ready",
                storage_path=source.relative_to(workspace).as_posix(),
                file_size=source.stat().st_size,
                sha256="a" * 64,
                source_name="best.pt",
                created_by_id="admin-id",
            )
        )
        database.commit()
    return app, admin, viewer, workspace


def test_model_artifact_api_permissions_download_and_stale_state(tmp_path):
    app, admin, viewer, workspace = setup_app(tmp_path)
    url = "/api/v1/models/model-id/artifacts"

    assert admin.post(url, json={"format": "onnx"}).status_code == 403
    assert viewer.post(url, headers=ORIGIN, json={"format": "onnx"}).status_code == 403
    created = admin.post(
        url,
        headers=ORIGIN,
        json={"format": "onnx", "image_size": 640, "dynamic": True},
    )
    assert created.status_code == 202
    artifact_id = created.json()["artifact"]["id"]
    assert created.json()["task"]["type"] == "convert_model"
    assert viewer.get(url).json()[0]["status"] == "queued"

    target = workspace / "models" / "model-id" / "artifacts" / "model.onnx"
    target.parent.mkdir()
    target.write_bytes(b"onnx")
    with app.state.model_artifact_service._session_factory() as database:
        artifact = database.get(ModelArtifact, artifact_id)
        artifact.status = "ready"
        artifact.storage_path = target.relative_to(workspace).as_posix()
        artifact.file_size = target.stat().st_size
        artifact.sha256 = "b" * 64
        task = database.get(Task, artifact.task_id)
        task.status = "succeeded"
        database.commit()

    downloaded = viewer.get(f"/api/v1/model-artifacts/{artifact_id}/download")
    assert downloaded.status_code == 200 and downloaded.content == b"onnx"
    assert 'filename="detector-onnx-' in downloaded.headers["content-disposition"]
    assert viewer.delete(
        f"/api/v1/model-artifacts/{artifact_id}", headers=ORIGIN
    ).status_code == 403

    with app.state.model_artifact_service._session_factory() as database:
        model = database.get(InferenceModel, "model-id")
        model.sha256 = "c" * 64
        database.commit()
    assert admin.get(url).json()[0]["status"] == "stale"
    assert admin.get(f"/api/v1/model-artifacts/{artifact_id}/download").status_code == 409
    assert admin.delete(
        f"/api/v1/model-artifacts/{artifact_id}", headers=ORIGIN
    ).status_code == 204
