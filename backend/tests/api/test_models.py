from datetime import datetime

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import (
    OFFICIAL_YOLO11_SYSTEM_KEY,
    InferenceModel,
    ModelProject,
    Task,
    User,
)
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
                User(
                    id="viewer-id",
                    username="viewer",
                    username_normalized="viewer",
                    password_hash=password_hash,
                    status="active",
                ),
                User(
                    id="outsider-id",
                    username="outsider",
                    username_normalized="outsider",
                    password_hash=password_hash,
                    status="active",
                ),
                User(
                    id="disabled-id",
                    username="disabled",
                    username_normalized="disabled",
                    password_hash=password_hash,
                    status="disabled",
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
        json={"name": "Official YOLO", "description": "archive", "tags": ["官方", "GOAT"]},
    )
    assert created.status_code == 201
    assert created.json()["access"]["role"] == "owner"
    assert created.json()["access"]["source"] == "owner"
    model_project_id = created.json()["id"]
    assert admin.post(
        f"/api/v1/model-projects/{model_project_id}/members",
        headers=ORIGIN,
        json={"username": "editor", "role": "viewer"},
    ).status_code == 201
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
    assert archive["tags"] == ["GOAT", "官方"]
    assert "created_at" in archive and "updated_at" in archive
    project_models = editor.get(
        f"/api/v1/model-projects/{model_project_id}/models"
    )
    assert project_models.status_code == 200
    assert project_models.json()[0]["name"] == "YOLO helmet"
    listed = editor.get("/api/v1/models")
    assert listed.status_code == 200
    assert listed.json()[0]["name"] == "YOLO helmet"
    assert TestClient(_app).get("/api/v1/model-projects").status_code == 401
    assert admin.get("/api/v1/model-project-tags").json() == ["GOAT", "内置", "官方"]
    model_id = response.json()["model"]["id"]
    service = _app.state.model_service
    target = service.workspace / "models" / model_id / "yolo.pt"
    target.parent.mkdir(parents=True)
    target.write_bytes(b"downloadable-weights")
    with service._session_factory() as database:
        model = database.get(InferenceModel, model_id)
        model.status = "ready"
        model.storage_path = target.relative_to(service.workspace).as_posix()
        database.commit()
    downloaded = admin.get(f"/api/v1/models/{model_id}/download")
    assert downloaded.status_code == 200 and downloaded.content == b"downloadable-weights"


def test_official_project_is_always_last_in_project_list(tmp_path):
    app, admin, _editor, _project_id = make_app(tmp_path)
    older = admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Older archive", "description": ""},
    ).json()
    newer = admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Newer archive", "description": ""},
    ).json()
    with Session(app.state.auth_service.engine) as session:
        official = session.scalar(
            select(ModelProject).where(
                ModelProject.system_key == OFFICIAL_YOLO11_SYSTEM_KEY
            )
        )
        assert official is not None
        official.created_at = datetime(2099, 1, 1)
        official.updated_at = datetime(2099, 1, 1)
        official_id = official.id
        session.commit()

    listed = admin.get("/api/v1/model-projects")

    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [
        newer["id"],
        older["id"],
        official_id,
    ]


def test_model_registration_requires_admin_and_valid_source_shape(tmp_path):
    _app, admin, editor, project_id = make_app(tmp_path)
    created = admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Admin archive", "description": ""},
    ).json()
    assert admin.post(
        f"/api/v1/model-projects/{created['id']}/members",
        headers=ORIGIN,
        json={"username": "editor", "role": "viewer"},
    ).status_code == 201
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


def test_model_project_memberships_and_private_visibility(tmp_path):
    app, admin, owner, _project_id = make_app(tmp_path)
    viewer = client_for(app, "viewer")
    outsider = client_for(app, "outsider")
    project = owner.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Private models", "description": ""},
    ).json()
    project_id = project["id"]

    assert project["access"]["role"] == "owner"
    admin_access = admin.get(f"/api/v1/model-projects/{project_id}").json()["access"]
    assert admin_access["role"] is None
    assert admin_access["source"] == "system_admin"
    assert outsider.get("/api/v1/model-projects").json() == [
        item
        for item in outsider.get("/api/v1/model-projects").json()
        if item["system_key"] is not None
    ]
    assert outsider.get(f"/api/v1/model-projects/{project_id}").status_code == 404
    added = owner.post(
        f"/api/v1/model-projects/{project_id}/members",
        headers=ORIGIN,
        json={"username": "viewer", "role": "viewer"},
    )
    assert added.status_code == 201
    assert viewer.get(f"/api/v1/model-projects/{project_id}").json()["access"]["role"] == "viewer"
    assert viewer.patch(
        f"/api/v1/model-projects/{project_id}",
        headers=ORIGIN,
        json={"name": "Denied", "description": "", "version": 1},
    ).status_code == 403
    assert owner.patch(
        f"/api/v1/model-projects/{project_id}/members/viewer-id",
        headers=ORIGIN,
        json={"role": "editor"},
    ).json()["role"] == "editor"
    assert owner.post(
        f"/api/v1/model-projects/{project_id}/members",
        headers=ORIGIN,
        json={"username": "disabled", "role": "viewer"},
    ).status_code == 422
    assert owner.delete(
        f"/api/v1/model-projects/{project_id}/members/viewer-id", headers=ORIGIN
    ).status_code == 204
    assert viewer.get(f"/api/v1/model-projects/{project_id}").status_code == 404


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


def test_official_project_is_read_only_for_users_and_maintainable_by_admin(tmp_path):
    app, admin, editor, _project_id = make_app(tmp_path)
    assert admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "training", "description": "", "series_type": "training"},
    ).status_code == 422
    official = next(
        item for item in admin.get("/api/v1/model-projects").json()
        if item["system_key"] == "official_yolo11"
    )
    ordinary = next(
        item for item in editor.get("/api/v1/model-projects").json()
        if item["id"] == official["id"]
    )
    assert ordinary["access"] == {
        "role": "viewer",
        "source": "system_resource",
        "permissions": ["artifact.download", "artifact.read", "project.read", "task.read"],
    }
    assert editor.patch(
        f"/api/v1/model-projects/{official['id']}",
        headers=ORIGIN,
        json={
            "name": official["name"],
            "description": "denied",
            "version": official["version"],
        },
    ).status_code == 403
    assert editor.post(
        f"/api/v1/model-projects/{official['id']}/models",
        headers=ORIGIN,
        json={"name": "forbidden", "source_path": "models/yolo.pt"},
    ).status_code == 403
    updated = admin.patch(
        f"/api/v1/model-projects/{official['id']}",
        headers=ORIGIN,
        json={
            "name": official["name"],
            "description": "maintained",
            "version": official["version"],
        },
    )
    assert updated.status_code == 200
    assert admin.post(
        f"/api/v1/model-projects/{official['id']}/members",
        headers=ORIGIN,
        json={"username": "editor", "role": "editor"},
    ).status_code == 403
    assert admin.delete(
        f"/api/v1/model-projects/{official['id']}", headers=ORIGIN
    ).status_code == 403
    imported = admin.post(
        f"/api/v1/model-projects/{official['id']}/models",
        headers=ORIGIN,
        json={"name": "YOLO11", "source_path": "models/yolo.pt"},
    )
    assert imported.status_code == 202
    model_id = imported.json()["model"]["id"]
    stored = app.state.model_service.workspace / "models" / model_id / "yolo.pt"
    stored.parent.mkdir(parents=True)
    stored.write_bytes(b"official-weights")
    with app.state.model_service._session_factory() as database:
        model = database.get(InferenceModel, model_id)
        model.status = "ready"
        model.storage_path = stored.relative_to(app.state.model_service.workspace).as_posix()
        model.file_size = stored.stat().st_size
        database.commit()
    downloaded = editor.get(f"/api/v1/models/{model_id}/download")
    assert downloaded.status_code == 200
    assert downloaded.content == b"official-weights"
    assert admin.patch(
        f"/api/v1/models/{model_id}",
        headers=ORIGIN,
        json={"name": "YOLO11 maintained", "description": "", "version": 1},
    ).status_code == 200
    assert admin.delete(f"/api/v1/models/{model_id}", headers=ORIGIN).status_code == 204


def test_unused_model_project_tags_are_pruned_after_update_and_delete(tmp_path):
    _app, admin, _editor, _project_id = make_app(tmp_path)
    first = admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "First tagged", "description": "", "tags": ["共享", "仅一号"]},
    ).json()
    second = admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Second tagged", "description": "", "tags": ["共享"]},
    ).json()

    updated = admin.patch(
        f"/api/v1/model-projects/{first['id']}",
        headers=ORIGIN,
        json={"name": first["name"], "description": "", "version": 1, "tags": ["替换"]},
    )
    assert updated.status_code == 200
    assert "仅一号" not in admin.get("/api/v1/model-project-tags").json()
    assert "共享" in admin.get("/api/v1/model-project-tags").json()

    assert admin.delete(f"/api/v1/model-projects/{second['id']}", headers=ORIGIN).status_code == 204
    assert "共享" not in admin.get("/api/v1/model-project-tags").json()
    assert admin.delete(f"/api/v1/model-projects/{first['id']}", headers=ORIGIN).status_code == 204
    assert "替换" not in admin.get("/api/v1/model-project-tags").json()


def test_active_model_capability_task_blocks_model_deletion(tmp_path):
    app, admin, _editor, _project_id = make_app(tmp_path)
    project = admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Active conversion", "description": ""},
    ).json()
    model = admin.post(
        f"/api/v1/model-projects/{project['id']}/models",
        headers=ORIGIN,
        json={"name": "YOLO", "source_path": "models/yolo.pt"},
    ).json()["model"]
    service = app.state.model_service
    with service._session_factory() as database:
        database.add(
            Task(
                id="active-conversion",
                model_project_id=project["id"],
                submitted_by_id="admin-id",
                type="convert_model",
                status="running",
                payload=f'{{"model_id":"{model["id"]}"}}',
            )
        )
        database.commit()

    assert admin.delete(f"/api/v1/models/{model['id']}", headers=ORIGIN).status_code == 409

    with service._session_factory() as database:
        database.get(Task, "active-conversion").status = "canceled"
        database.commit()
    assert admin.delete(f"/api/v1/models/{model['id']}", headers=ORIGIN).status_code == 204
