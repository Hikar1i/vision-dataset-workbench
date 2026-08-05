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
    created = admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Official YOLO", "description": "archive"},
    )
    assert created.status_code == 201
    model_project_id = created.json()["id"]
    response = admin.post(
        f"/api/v1/model-projects/{model_project_id}/models",
        headers=ORIGIN,
        json={"name": "YOLO helmet", "description": "detect", "source_path": "models/yolo.pt"},
    )

    assert response.status_code == 202
    assert response.json()["model"]["status"] == "copying"
    assert response.json()["model"]["model_project_id"] == model_project_id
    assert response.json()["task"]["project_id"] is None
    assert response.json()["task"]["model_project_id"] == model_project_id
    assert response.json()["task"]["type"] == "import_model"
    projects = editor.get("/api/v1/model-projects")
    assert projects.status_code == 200
    archive = next(item for item in projects.json() if item["id"] == model_project_id)
    assert archive["can_manage"] is False
    project_models = editor.get(
        f"/api/v1/model-projects/{model_project_id}/models"
    )
    assert project_models.status_code == 200
    assert project_models.json()[0]["name"] == "YOLO helmet"
    listed = editor.get("/api/v1/models")
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "YOLO helmet"
    assert TestClient(_app).get("/api/v1/model-projects").status_code == 401


def test_model_registration_requires_admin_and_valid_source_shape(tmp_path):
    _app, admin, editor, project_id = make_app(tmp_path)
    created = admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Admin archive", "description": ""},
    ).json()
    url = f"/api/v1/model-projects/{created['id']}/models"

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


def test_model_projects_are_versioned_and_logically_deleted(tmp_path):
    _app, admin, editor, _project_id = make_app(tmp_path)
    created = editor.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Fire models", "description": "first"},
    )
    assert created.status_code == 201
    project = created.json()
    assert project["series_type"] == "archive"
    assert project["can_manage"] is True
    assert admin.patch(
        f"/api/v1/model-projects/{project['id']}",
        headers=ORIGIN,
        json={"name": "Fire models v2", "description": "updated", "version": 1},
    ).status_code == 200
    assert editor.patch(
        f"/api/v1/model-projects/{project['id']}",
        headers=ORIGIN,
        json={"name": "stale", "description": "", "version": 1},
    ).status_code == 409
    assert editor.delete(
        f"/api/v1/model-projects/{project['id']}", headers=ORIGIN
    ).status_code == 204
    assert editor.get(f"/api/v1/model-projects/{project['id']}").status_code == 404
    assert editor.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Fire models v2", "description": "reused"},
    ).status_code == 201


def test_training_and_temporary_projects_are_not_manually_writable(tmp_path):
    _app, admin, _editor, _project_id = make_app(tmp_path)
    assert admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "training", "description": "", "series_type": "training"},
    ).status_code == 422
    temporary = next(
        item for item in admin.get("/api/v1/model-projects").json()
        if item["system_key"] == "temporary"
    )
    assert admin.post(
        f"/api/v1/model-projects/{temporary['id']}/models",
        headers=ORIGIN,
        json={"name": "forbidden", "source_path": "models/yolo.pt"},
    ).status_code == 403
