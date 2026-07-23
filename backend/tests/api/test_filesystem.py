from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import User
from vision_dataset_workbench.security.passwords import hash_password

PASSWORD = "correct horse battery staple"
ORIGIN = {"Origin": "http://testserver"}


def make_client(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    home.mkdir()
    (home / "clips").mkdir()
    (home / "one.MP4").write_bytes(b"video")
    (home / "notes.txt").write_text("not video")
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
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
    client = TestClient(create_app(RuntimeSettings(home=home, workspace=workspace)))
    return client, home, workspace


def login(client):
    return client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": "admin", "password": PASSWORD},
    )


def test_authenticated_video_browser_filters_and_hides_workspace(tmp_path):
    client, _home, _workspace = make_client(tmp_path)

    assert client.get("/api/v1/filesystem").status_code == 401
    assert login(client).status_code == 200
    response = client.get("/api/v1/filesystem", params={"path": ".", "kind": "video"})

    assert response.status_code == 200
    assert [(item["name"], item["type"]) for item in response.json()["items"]] == [
        ("clips", "directory"),
        ("one.MP4", "file"),
    ]
    assert all(".vision-dataset-workbench" not in item["path"] for item in response.json()["items"])
    assert all(not item["path"].startswith("/") for item in response.json()["items"])


def test_browser_rejects_escapes_and_creates_directory(tmp_path):
    client, home, workspace = make_client(tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "escape").symlink_to(outside, target_is_directory=True)
    assert login(client).status_code == 200

    assert client.get("/api/v1/filesystem", params={"path": ".."}).status_code == 400
    assert client.get("/api/v1/filesystem", params={"path": "escape"}).status_code == 400
    assert (
        client.get(
            "/api/v1/filesystem",
            params={"path": workspace.relative_to(home).as_posix()},
        ).status_code
        == 400
    )
    assert (
        client.post(
            "/api/v1/filesystem/directories",
            json={"parent": ".", "name": "new"},
        ).status_code
        == 403
    )
    created = client.post(
        "/api/v1/filesystem/directories",
        headers=ORIGIN,
        json={"parent": ".", "name": "new"},
    )
    assert created.status_code == 201
    assert created.json() == {"path": "new", "display_path": "~/new"}
    assert (home / "new").is_dir()
