from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import User
from vision_dataset_workbench.security.passwords import hash_password

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "new correct horse battery"
ORIGIN = {"Origin": "http://testserver"}


def make_app(tmp_path):
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
    return create_app(RuntimeSettings(home=home, workspace=workspace))


def login(client, username="admin", password=PASSWORD):
    return client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": username, "password": password},
    )


def create_user(client, username="colleague"):
    return client.post(
        "/api/v1/admin/users", headers=ORIGIN, json={"username": username}
    )


def act(client, user_id, action):
    return client.post(f"/api/v1/admin/users/{user_id}/{action}", headers=ORIGIN)


def test_admin_provisions_user_and_initial_password_is_one_time(tmp_path):
    app = make_app(tmp_path)
    admin = TestClient(app)
    user = TestClient(app)
    assert login(admin).status_code == 200

    created = create_user(admin)

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "active"
    assert body["must_change_password"] is True
    assert len(body["initial_password"]) >= 12
    listed = admin.get("/api/v1/admin/users").json()["items"]
    assert all("initial_password" not in item for item in listed)

    assert login(user, "colleague", body["initial_password"]).status_code == 200
    assert user.get("/api/v1/auth/me").json()["must_change_password"] is True
    assert user.get("/api/v1/projects").status_code == 403
    changed = user.put(
        "/api/v1/auth/password",
        headers=ORIGIN,
        json={"current_password": body["initial_password"], "new_password": NEW_PASSWORD},
    )
    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False
    assert user.get("/api/v1/projects").status_code == 200


def test_duplicate_disable_enable_and_reset(tmp_path):
    app = make_app(tmp_path)
    admin = TestClient(app)
    user = TestClient(app)
    assert login(admin).status_code == 200
    first = create_user(admin, "New.User")
    assert first.status_code == 201
    assert create_user(admin, "new.user").status_code == 409
    user_id = first.json()["id"]
    initial_password = first.json()["initial_password"]
    assert login(user, "new.user", initial_password).status_code == 200

    assert act(admin, user_id, "disable").json()["status"] == "disabled"
    assert user.get("/api/v1/auth/me").status_code == 401
    assert act(admin, user_id, "enable").json()["status"] == "active"
    reset = admin.post(
        f"/api/v1/admin/users/{user_id}/reset-password", headers=ORIGIN
    )
    assert reset.status_code == 200
    assert reset.json()["initial_password"] != initial_password
    assert login(user, "new.user", initial_password).status_code == 401
    assert login(user, "new.user", reset.json()["initial_password"]).status_code == 200


def test_non_admin_forbidden_and_admin_account_immutable(tmp_path):
    app = make_app(tmp_path)
    admin = TestClient(app)
    user = TestClient(app)
    assert login(admin).status_code == 200
    created = create_user(admin).json()
    assert login(user, "colleague", created["initial_password"]).status_code == 200
    assert user.get("/api/v1/admin/users").status_code == 403

    admin_id = admin.get("/api/v1/auth/me").json()["id"]
    assert act(admin, admin_id, "disable").status_code == 409
    assert admin.post(
        f"/api/v1/admin/users/{admin_id}/reset-password", headers=ORIGIN
    ).status_code == 409
