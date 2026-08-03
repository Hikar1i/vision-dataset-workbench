from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import Task, User
from vision_dataset_workbench.security.passwords import hash_password

PASSWORD = "correct horse battery staple"
ORIGIN = {"Origin": "http://testserver"}


def make_app(tmp_path, mode="multi"):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects").mkdir(parents=True)
    database_path = workspace / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    password_hash = hash_password(PASSWORD)
    with Session(engine) as session:
        for username, admin, status in (
            ("admin", True, "active"),
            ("creator", False, "active"),
            ("editor", False, "active"),
            ("viewer", False, "active"),
            ("outsider", False, "active"),
            ("disabled", False, "disabled"),
        ):
            session.add(
                User(
                    id=f"{username}-id",
                    username=username,
                    username_normalized=username,
                    password_hash=password_hash,
                    status=status,
                    is_system_admin=admin,
                )
            )
        session.commit()
    engine.dispose()
    settings = RuntimeSettings(home=home, workspace=workspace, app_mode=mode)
    return create_app(settings), settings


def client_for(app, username):
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return client


def create_project(client, name="Project"):
    return client.post(
        "/api/v1/projects",
        headers=ORIGIN,
        json={"name": name, "description": "description"},
    )


def add_member(client, project_id, username, role):
    return client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=ORIGIN,
        json={"username": username, "role": role},
    )


def test_project_creation_and_private_lists(tmp_path):
    app, _ = make_app(tmp_path)
    creator = client_for(app, "creator")
    outsider = client_for(app, "outsider")
    admin = client_for(app, "admin")

    created = create_project(creator, " Same name ")
    duplicate_name = create_project(creator, "Same name")
    project_id = created.json()["id"]

    assert created.status_code == duplicate_name.status_code == 201
    assert created.json()["name"] == "Same name"
    assert created.json()["role"] == "owner"
    assert creator.get("/api/v1/projects").json()["total"] == 2
    assert outsider.get("/api/v1/projects").json()["total"] == 0
    assert admin.get("/api/v1/projects").json()["total"] == 0
    assert outsider.get(f"/api/v1/projects/{project_id}").status_code == 404


def test_editor_updates_viewer_reads_and_version_conflicts(tmp_path):
    app, _ = make_app(tmp_path)
    creator = client_for(app, "creator")
    editor = client_for(app, "editor")
    viewer = client_for(app, "viewer")
    project = create_project(creator).json()
    project_id = project["id"]
    assert add_member(creator, project_id, "editor", "editor").status_code == 201
    assert add_member(creator, project_id, "viewer", "viewer").status_code == 201

    updated = editor.patch(
        f"/api/v1/projects/{project_id}",
        headers=ORIGIN,
        json={"name": "Changed", "description": "new", "version": 1},
    )
    denied = viewer.patch(
        f"/api/v1/projects/{project_id}",
        headers=ORIGIN,
        json={"name": "No", "description": "", "version": 2},
    )
    stale = creator.patch(
        f"/api/v1/projects/{project_id}",
        headers=ORIGIN,
        json={"name": "Stale", "description": "", "version": 1},
    )

    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert viewer.get(f"/api/v1/projects/{project_id}").json()["role"] == "viewer"
    assert denied.status_code == 403
    assert stale.status_code == 409


def test_owner_manages_members_and_other_roles_cannot(tmp_path):
    app, _ = make_app(tmp_path)
    creator = client_for(app, "creator")
    editor = client_for(app, "editor")
    project_id = create_project(creator).json()["id"]
    assert add_member(creator, project_id, "editor", "editor").status_code == 201

    listed = editor.get(f"/api/v1/projects/{project_id}/members")
    forbidden = add_member(editor, project_id, "viewer", "viewer")
    disabled = add_member(creator, project_id, "disabled", "viewer")
    changed = creator.patch(
        f"/api/v1/projects/{project_id}/members/editor-id",
        headers=ORIGIN,
        json={"role": "viewer"},
    )
    removed = creator.delete(
        f"/api/v1/projects/{project_id}/members/editor-id", headers=ORIGIN
    )

    assert listed.status_code == 200
    assert [item["role"] for item in listed.json()] == ["owner", "editor"]
    assert forbidden.status_code == 403
    assert disabled.status_code == 422
    assert changed.json()["role"] == "viewer"
    assert removed.status_code == 204


def test_project_writes_require_same_origin(tmp_path):
    app, _ = make_app(tmp_path)
    creator = client_for(app, "creator")

    assert creator.post(
        "/api/v1/projects", json={"name": "Project", "description": ""}
    ).status_code == 403


def test_only_owner_can_delete_project_and_archive_it(tmp_path):
    app, _ = make_app(tmp_path)
    creator = client_for(app, "creator")
    editor = client_for(app, "editor")
    viewer = client_for(app, "viewer")
    project_id = create_project(creator).json()["id"]
    assert add_member(creator, project_id, "editor", "editor").status_code == 201
    assert add_member(creator, project_id, "viewer", "viewer").status_code == 201

    assert editor.delete(f"/api/v1/projects/{project_id}", headers=ORIGIN).status_code == 403
    assert viewer.delete(f"/api/v1/projects/{project_id}", headers=ORIGIN).status_code == 403
    assert creator.delete(f"/api/v1/projects/{project_id}").status_code == 403
    assert creator.delete(f"/api/v1/projects/{project_id}", headers=ORIGIN).status_code == 204

    assert creator.get(f"/api/v1/projects/{project_id}").status_code == 404
    assert creator.get("/api/v1/projects").json()["total"] == 0
    archived = app.state.workspace / ".deleted" / "projects" / project_id / "project"
    assert (archived / "project_metadata.json").is_file()


def test_active_project_task_blocks_delete(tmp_path):
    app, _ = make_app(tmp_path)
    creator = client_for(app, "creator")
    project_id = create_project(creator).json()["id"]
    with Session(app.state.auth_service.engine) as session:
        session.add(
            Task(
                project_id=project_id,
                submitted_by_id="creator-id",
                type="copy_video",
                status="running",
            )
        )
        session.commit()

    response = creator.delete(f"/api/v1/projects/{project_id}", headers=ORIGIN)

    assert response.status_code == 409
    assert "active tasks" in response.json()["detail"]


def test_single_mode_admin_has_owner_equivalent_access(tmp_path):
    app, settings = make_app(tmp_path)
    creator = client_for(app, "creator")
    project_id = create_project(creator).json()["id"]

    single_app = create_app(
        RuntimeSettings(
            home=settings.home,
            workspace=settings.workspace,
            app_mode="single",
        )
    )
    admin = client_for(single_app, "admin")

    assert admin.get(f"/api/v1/projects/{project_id}").json()["role"] == "owner"
    assert add_member(admin, project_id, "viewer", "viewer").status_code == 201
