from fastapi.testclient import TestClient

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.setup.tokens import SetupToken
from vision_dataset_workbench.storage.locator import WorkspaceLocator


def make_client(tmp_path):
    home = tmp_path / "home"
    (home / "datasets").mkdir(parents=True)
    token = SetupToken.create()
    app = create_app(
        RuntimeSettings(home=home, workspace=None),
        setup_token=token,
        locator=WorkspaceLocator(tmp_path / "instance.json"),
    )
    return TestClient(app), token.plaintext, home


def test_setup_status_and_directory_listing(tmp_path):
    client, token, _home = make_client(tmp_path)

    assert client.get("/api/v1/setup/status").json() == {"initialized": False}
    assert client.get("/api/v1/setup/directories").status_code == 403
    response = client.get(
        "/api/v1/setup/directories", params={"path": "."}, headers={"X-Setup-Token": token}
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["path"] == "datasets"


def test_create_directory_and_initialize(tmp_path):
    client, token, home = make_client(tmp_path)
    headers = {"X-Setup-Token": token}

    created = client.post(
        "/api/v1/setup/directories",
        headers=headers,
        json={"parent": "datasets", "name": "workbench"},
    )
    initialized = client.post(
        "/api/v1/setup/initialize",
        headers=headers,
        json={
            "parent": "datasets/workbench",
            "username": "admin",
            "password": "correct horse battery staple",
        },
    )

    assert created.status_code == 201
    assert initialized.status_code == 201
    assert (home / "datasets/workbench/.vision-dataset-workbench/db/workbench.sqlite3").exists()
    assert client.get("/api/v1/setup/status").json() == {"initialized": True}
    assert client.get("/api/v1/setup/directories", headers=headers).status_code == 403
    assert (
        client.post(
            "/api/v1/auth/login",
            headers={"Origin": "http://testserver"},
            json={
                "username": "admin",
                "password": "correct horse battery staple",
            },
        ).status_code
        == 200
    )
