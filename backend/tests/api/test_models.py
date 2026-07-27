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
    (home / "models" / "grounding-dino").mkdir(parents=True)
    (home / "models" / "grounding-dino" / "config.json").write_text("{}")
    (home / "models" / "yolo.pt").write_bytes(b"weights")
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
        json={"name": "YOLO helmet", "kind": "yolo", "source_path": "models/yolo.pt"},
    )

    assert response.status_code == 202
    assert response.json()["model"]["status"] == "copying"
    assert response.json()["task"]["type"] == "import_model"
    listed = editor.get("/api/v1/models")
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "YOLO helmet"


def test_model_registration_requires_admin_and_valid_source_shape(tmp_path):
    _app, admin, editor, project_id = make_app(tmp_path)
    url = f"/api/v1/projects/{project_id}/models"

    assert editor.post(
        url,
        headers=ORIGIN,
        json={"name": "Forbidden", "kind": "yolo", "source_path": "models/yolo.pt"},
    ).status_code == 403
    assert admin.post(
        url,
        headers=ORIGIN,
        json={"name": "Bad YOLO", "kind": "yolo", "source_path": "models/grounding-dino"},
    ).status_code == 422
    assert admin.post(
        url,
        headers=ORIGIN,
        json={"name": "Bad DINO", "kind": "grounding_dino", "source_path": "models/yolo.pt"},
    ).status_code == 422
    assert admin.post(
        url,
        json={"name": "No origin", "kind": "yolo", "source_path": "models/yolo.pt"},
    ).status_code == 403
