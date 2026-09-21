from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import User
from vision_dataset_workbench.security.passwords import hash_password

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "new correct horse battery"
ORIGIN = {"Origin": "http://testserver"}


def make_client(tmp_path, *, mode="multi", must_change_password=False):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    database_path = workspace / "db" / "workbench.sqlite3"
    home.mkdir()
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
                must_change_password=must_change_password,
            )
        )
        session.commit()
    engine.dispose()
    app = create_app(
        RuntimeSettings(
            home=home,
            workspace=workspace,
            app_mode=mode,
        )
    )
    return TestClient(app)


def login(client, password=PASSWORD, headers=ORIGIN):
    return client.post(
        "/api/v1/auth/login",
        headers=headers,
        json={"username": "admin", "password": password},
    )


def test_status_login_cookie_and_current_user(tmp_path):
    client = make_client(tmp_path)

    assert client.get("/api/v1/auth/status").json() == {"mode": "multi"}
    response = login(client)

    assert response.status_code == 200
    assert response.json() == {
        "id": response.json()["id"],
        "username": "admin",
        "status": "active",
        "is_system_admin": True,
        "must_change_password": False,
    }
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Max-Age=604800" in cookie
    assert "Secure" not in cookie
    assert client.get("/api/v1/auth/me").json()["username"] == "admin"


def test_logout_and_password_change_replace_sessions(tmp_path):
    client = make_client(tmp_path)
    assert login(client).status_code == 200

    changed = client.put(
        "/api/v1/auth/password",
        headers=ORIGIN,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
    )

    assert changed.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 200
    client.post("/api/v1/auth/logout", headers=ORIGIN)
    assert client.get("/api/v1/auth/me").status_code == 401
    assert login(client).status_code == 401
    assert login(client, NEW_PASSWORD).status_code == 200


def test_required_password_change_accepts_only_new_password(tmp_path):
    client = make_client(tmp_path, must_change_password=True)
    assert login(client).status_code == 200

    changed = client.put(
        "/api/v1/auth/password",
        headers=ORIGIN,
        json={"new_password": NEW_PASSWORD},
    )

    assert changed.status_code == 200
    assert changed.json()["must_change_password"] is False
    assert login(client, NEW_PASSWORD).status_code == 200


def test_ordinary_password_change_without_current_password_is_unprocessable(tmp_path):
    client = make_client(tmp_path)
    assert login(client).status_code == 200

    changed = client.put(
        "/api/v1/auth/password",
        headers=ORIGIN,
        json={"new_password": NEW_PASSWORD},
    )

    assert changed.status_code == 422
    assert changed.json() == {"detail": "current password is required"}


def test_browser_writes_require_exact_same_origin(tmp_path):
    client = make_client(tmp_path)

    assert login(client, headers={}).status_code == 403
    assert login(client, headers={"Origin": "http://other.example"}).status_code == 403
    assert login(client).status_code == 200
    assert client.post("/api/v1/auth/logout").status_code == 403


def test_login_errors_are_generic(tmp_path):
    client = make_client(tmp_path)

    missing = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": "missing", "password": PASSWORD},
    )
    wrong = login(client, "wrong password")

    assert missing.status_code == wrong.status_code == 401
    assert missing.json() == wrong.json() == {"detail": "invalid username or password"}
