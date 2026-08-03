from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import User
from vision_dataset_workbench.security.passwords import hash_password

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


def make_app(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    home.mkdir()
    (home / "models").mkdir(parents=True)
    (home / "models" / "yolo.pt").write_bytes(b"weights")
    (home / "models" / "yolo.onnx").write_bytes(b"weights")
    (workspace / "projects").mkdir(parents=True)
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    password_hash = hash_password(PASSWORD)
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    id="admin-id",
                    username="admin",
                    username_normalized="admin",
                    password_hash=password_hash,
                    status="active",
                    is_system_admin=True,
                ),
                User(
                    id="editor-id",
                    username="editor",
                    username_normalized="editor",
                    password_hash=password_hash,
                    status="active",
                ),
            ]
        )
        session.commit()
    engine.dispose()
    app = create_app(RuntimeSettings(home=home, workspace=workspace))
    admin = client_for(app, "admin")
    project_id = admin.post(
        "/api/v1/projects",
        headers=ORIGIN,
        json={"name": "Project", "description": ""},
    ).json()["id"]
    assert admin.post(
        f"/api/v1/projects/{project_id}/members",
        headers=ORIGIN,
        json={"username": "editor", "role": "editor"},
    ).status_code == 201
    return app, admin, client_for(app, "editor"), project_id


def client_for(app, username):
    client = TestClient(app)
    assert client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": username, "password": PASSWORD},
    ).status_code == 200
    return client


def test_admin_registers_models_and_members_list_them(tmp_path):
    _app, admin, editor, project_id = make_app(tmp_path)
    response = admin.post(
        f"/api/v1/projects/{project_id}/models",
        headers=ORIGIN,
        json={"name": "YOLO helmet", "source_path": "models/yolo.pt"},
    )

    assert response.status_code == 202
    assert response.json()["model"]["status"] == "copying"
    assert response.json()["model"]["model_project_id"] == (
        "00000000-0000-0000-0000-000000000001"
    )
    assert response.json()["task"]["type"] == "import_model"
    projects = editor.get("/api/v1/model-projects")
    assert projects.status_code == 200
    assert projects.json()[0]["system_key"] == "temporary"
    project_models = editor.get(
        f"/api/v1/model-projects/{projects.json()[0]['id']}/models"
    )
    assert project_models.status_code == 200
    assert project_models.json()[0]["name"] == "YOLO helmet"
    listed = editor.get("/api/v1/models")
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "YOLO helmet"
    assert TestClient(_app).get("/api/v1/model-projects").status_code == 401


def test_model_registration_requires_admin_and_valid_source_shape(tmp_path):
    _app, admin, editor, project_id = make_app(tmp_path)
    url = f"/api/v1/projects/{project_id}/models"

    assert editor.post(
        url,
        headers=ORIGIN,
        json={"name": "Forbidden", "source_path": "models/yolo.pt"},
    ).status_code == 403
    assert admin.post(
        url,
        headers=ORIGIN,
        json={"name": "Bad YOLO", "source_path": "models"},
    ).status_code == 422
    assert admin.post(
        url,
        headers=ORIGIN,
        json={"name": "Bad ONNX", "source_path": "models/yolo.onnx"},
    ).status_code == 422
    assert admin.post(
        url,
        json={"name": "No origin", "source_path": "models/yolo.pt"},
    ).status_code == 403
