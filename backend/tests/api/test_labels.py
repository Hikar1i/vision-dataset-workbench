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
    (workspace / "projects").mkdir(parents=True)
    database_path = workspace / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    password_hash = hash_password(PASSWORD)
    with Session(engine) as session:
        for username in ("creator", "editor", "viewer", "outsider"):
            session.add(
                User(
                    id=f"{username}-id",
                    username=username,
                    username_normalized=username,
                    password_hash=password_hash,
                    status="active",
                )
            )
        session.commit()
    engine.dispose()
    return create_app(RuntimeSettings(home=home, workspace=workspace))


def client_for(app, username):
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return client


def create_project(client):
    return client.post(
        "/api/v1/projects",
        headers=ORIGIN,
        json={"name": "Project", "description": ""},
    )


def add_member(client, project_id, username, role):
    return client.post(
        f"/api/v1/projects/{project_id}/members",
        headers=ORIGIN,
        json={"username": username, "role": role},
    )


def create_label(client, project_id, name, color="#16866f", description_zh=""):
    return client.post(
        f"/api/v1/projects/{project_id}/labels",
        headers=ORIGIN,
        json={"name": name, "color": color, "description_zh": description_zh},
    )


def test_owner_and_editor_manage_labels_while_viewer_is_read_only(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "creator")
    editor = client_for(app, "editor")
    viewer = client_for(app, "viewer")
    outsider = client_for(app, "outsider")
    project_id = create_project(owner).json()["id"]
    assert add_member(owner, project_id, "editor", "editor").status_code == 201
    assert add_member(owner, project_id, "viewer", "viewer").status_code == 201

    helmet = create_label(owner, project_id, " Helmet ", description_zh=" 安全帽 ").json()
    person = create_label(editor, project_id, "person", "#17212b").json()

    assert helmet["name"] == "helmet"
    assert helmet["description_zh"] == "安全帽"
    assert [item["name"] for item in viewer.get(
        f"/api/v1/projects/{project_id}/labels"
    ).json()] == ["helmet", "person"]
    assert create_label(viewer, project_id, "dog").status_code == 403
    assert outsider.get(f"/api/v1/projects/{project_id}/labels").status_code == 404

    disabled = editor.patch(
        f"/api/v1/projects/{project_id}/labels/{helmet['id']}",
        headers=ORIGIN,
        json={"enabled": False, "version": helmet["version"]},
    )
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["version"] == 2

    described = editor.patch(
        f"/api/v1/projects/{project_id}/labels/{helmet['id']}",
        headers=ORIGIN,
        json={"description_zh": "防护头盔", "version": disabled.json()["version"]},
    )
    assert described.status_code == 200
    assert described.json()["description_zh"] == "防护头盔"
    assert viewer.patch(
        f"/api/v1/projects/{project_id}/labels/{helmet['id']}",
        headers=ORIGIN,
        json={"description_zh": "禁止修改", "version": described.json()["version"]},
    ).status_code == 403

    reordered = owner.put(
        f"/api/v1/projects/{project_id}/labels/order",
        headers=ORIGIN,
        json={"label_ids": [person["id"], helmet["id"]]},
    )
    assert reordered.status_code == 200
    assert [item["name"] for item in reordered.json()] == ["person", "helmet"]

    assert owner.delete(
        f"/api/v1/projects/{project_id}/labels/{person['id']}", headers=ORIGIN
    ).status_code == 204
    remaining = owner.get(f"/api/v1/projects/{project_id}/labels").json()
    assert [(item["name"], item["sort_order"]) for item in remaining] == [("helmet", 0)]


def test_label_validation_conflicts_and_order_membership(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "creator")
    project_id = create_project(owner).json()["id"]
    helmet = create_label(owner, project_id, "helmet").json()
    person = create_label(owner, project_id, "person").json()

    assert create_label(owner, project_id, "HELMET").status_code == 409
    assert create_label(owner, project_id, "安全帽").status_code == 422
    assert create_label(owner, project_id, "dog", "green").status_code == 422
    assert create_label(
        owner, project_id, "dog", description_zh="说明" * 33
    ).status_code == 422

    changed = owner.patch(
        f"/api/v1/projects/{project_id}/labels/{helmet['id']}",
        headers=ORIGIN,
        json={"name": "hard-hat", "color": "#78d2b8", "version": 1},
    )
    assert changed.status_code == 200
    stale = owner.patch(
        f"/api/v1/projects/{project_id}/labels/{helmet['id']}",
        headers=ORIGIN,
        json={"enabled": False, "version": 1},
    )
    assert stale.status_code == 409

    incomplete = owner.put(
        f"/api/v1/projects/{project_id}/labels/order",
        headers=ORIGIN,
        json={"label_ids": [person["id"]]},
    )
    duplicate = owner.put(
        f"/api/v1/projects/{project_id}/labels/order",
        headers=ORIGIN,
        json={"label_ids": [person["id"], person["id"]]},
    )
    assert incomplete.status_code == duplicate.status_code == 422


def test_label_writes_require_same_origin(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "creator")
    project_id = create_project(owner).json()["id"]

    assert owner.post(
        f"/api/v1/projects/{project_id}/labels",
        json={"name": "helmet", "color": "#16866f"},
    ).status_code == 403
