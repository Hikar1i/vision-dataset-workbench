from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import User
from vision_dataset_workbench.security.passwords import hash_password

PASSWORD = "correct horse battery staple"
ORIGIN = {"Origin": "http://testserver"}


def make_app(tmp_path, *, registration_enabled=True, mode="multi"):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    database_path = workspace / "db" / "workbench.sqlite3"
    home.mkdir(parents=True)
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    with Session(engine) as session:
        session.add(
            User(
                username="admin",
                username_normalized="admin",
                password_hash=hash_password(PASSWORD),
                status="active",
                is_system_admin=True,
            )
        )
        session.commit()
    engine.dispose()
    return create_app(
        RuntimeSettings(
            home=home,
            workspace=workspace,
            app_mode=mode,
            registration_enabled=registration_enabled,
        )
    )


def login(client, username="admin"):
    return client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": username, "password": PASSWORD},
    )


def register(client, username="colleague"):
    return client.post(
        "/api/v1/registrations",
        headers=ORIGIN,
        json={"username": username, "password": PASSWORD},
    )


def act(client, user_id, action):
    return client.post(
        f"/api/v1/admin/users/{user_id}/{action}", headers=ORIGIN
    )


def test_registration_requires_enabled_multi_mode(tmp_path):
    closed = TestClient(make_app(tmp_path / "closed", registration_enabled=False))
    assert register(closed).status_code == 403

    single = TestClient(
        make_app(tmp_path / "single", registration_enabled=True, mode="single")
    )
    assert register(single).status_code == 403


def test_pending_user_can_login_only_after_admin_approval(tmp_path):
    app = make_app(tmp_path)
    public = TestClient(app)
    admin = TestClient(app)
    registered = register(public)

    assert registered.status_code == 201
    assert registered.json()["status"] == "pending"
    assert login(public, "colleague").status_code == 401
    assert login(admin).status_code == 200
    assert act(admin, registered.json()["id"], "approve").status_code == 200
    assert login(public, "COLLEAGUE").status_code == 200


def test_registration_reserves_case_insensitive_username(tmp_path):
    client = TestClient(make_app(tmp_path))

    assert register(client, "New.User").status_code == 201
    duplicate = register(client, "new.user")

    assert duplicate.status_code == 409
    assert duplicate.json() == {"detail": "username already exists"}


def test_admin_lists_filters_and_changes_user_status(tmp_path):
    app = make_app(tmp_path)
    public = TestClient(app)
    admin = TestClient(app)
    first = register(public, "first").json()
    second = register(public, "second").json()
    assert login(admin).status_code == 200

    listed = admin.get(
        "/api/v1/admin/users", params={"status": "pending", "page_size": 1}
    )
    assert listed.status_code == 200
    assert listed.json()["total"] == 2
    assert len(listed.json()["items"]) == 1
    assert admin.get("/api/v1/admin/users", params={"status": ""}).status_code == 200
    assert act(admin, first["id"], "reject").json()["status"] == "rejected"
    assert act(admin, first["id"], "enable").json()["status"] == "active"
    assert act(admin, first["id"], "disable").json()["status"] == "disabled"
    assert act(admin, first["id"], "enable").json()["status"] == "active"
    assert act(admin, second["id"], "disable").status_code == 409


def test_non_admin_is_forbidden_and_disable_revokes_session(tmp_path):
    app = make_app(tmp_path)
    public = TestClient(app)
    admin = TestClient(app)
    user = register(public).json()
    assert login(admin).status_code == 200
    assert act(admin, user["id"], "approve").status_code == 200
    assert login(public, "colleague").status_code == 200

    assert public.get("/api/v1/admin/users").status_code == 403
    assert act(admin, user["id"], "disable").status_code == 200
    assert public.get("/api/v1/auth/me").status_code == 401


def test_last_active_administrator_cannot_be_disabled(tmp_path):
    client = TestClient(make_app(tmp_path))
    assert login(client).status_code == 200
    admin_id = client.get("/api/v1/auth/me").json()["id"]

    response = act(client, admin_id, "disable")

    assert response.status_code == 409
    assert response.json() == {"detail": "cannot disable the last active administrator"}
