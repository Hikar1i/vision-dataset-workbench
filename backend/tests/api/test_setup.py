from fastapi.testclient import TestClient
from PIL import Image

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.setup.tokens import SetupToken
from vision_dataset_workbench.storage.locator import WorkspaceLocator
from vision_dataset_workbench.worker import TaskWorker


def make_client(tmp_path):
    home = tmp_path / "home"
    (home / "datasets").mkdir(parents=True)
    (home / "archive").mkdir()
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
        "/api/v1/setup/directories",
        params={"path": ".", "search": "DATA"},
        headers={"X-Setup-Token": token},
    )

    assert response.status_code == 200
    assert [(item["path"], item["type"]) for item in response.json()["items"]] == [
        ("datasets", "dir")
    ]


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


def test_first_setup_wires_image_import_and_training_resources_without_restart(tmp_path):
    client, token, home = make_client(tmp_path)
    origin = {"Origin": "http://testserver"}
    source = home / "images"
    source.mkdir()
    Image.new("RGB", (16, 12), "red").save(source / "sample.png")
    password = "correct horse battery staple"
    initialized = client.post(
        "/api/v1/setup/initialize",
        headers={"X-Setup-Token": token},
        json={"parent": "datasets", "username": "admin", "password": password},
    )
    assert initialized.status_code == 201, initialized.text
    assert client.post(
        "/api/v1/auth/login", headers=origin,
        json={"username": "admin", "password": password},
    ).status_code == 200
    project = client.post(
        "/api/v1/projects", headers=origin,
        json={"name": "images", "project_type": "image"},
    )
    assert project.status_code == 201, project.text
    assert project.json()["project_type"] == "image"
    base = f"/api/v1/projects/{project.json()['id']}"
    assert client.patch(
        base, headers=origin,
        json={"name": "images", "version": 1, "project_type": "video"},
    ).status_code == 422
    preview = client.post(
        base + "/image-imports/preview", headers=origin,
        json={"root_path": "images", "format": "images"},
    )
    assert preview.status_code == 200, preview.text
    imported = client.post(
        base + "/image-imports", headers=origin,
        json={"root_path": "images", "format": "images", "fingerprint": preview.json()["fingerprint"]},
    )
    assert imported.status_code == 202, imported.text
    app = client.app
    worker = TaskWorker(app.state.auth_service.engine, app.state.settings, app.state.workspace)
    try:
        claimed = worker.claim_available()
        assert [task.id for task in claimed] == [imported.json()["task"]["id"]]
        worker.execute_task(claimed[0].id)
    finally:
        worker._executor.shutdown(wait=True)
    page = client.get(base + "/images")
    assert page.status_code == 200, page.text
    assert page.json()["total"] == 1
    assert page.json()["items"][0]["annotation_status"] == "pending"
    assert client.get(base + "/dataset-exports").status_code == 200
    resources = client.get("/api/v1/training/resources")
    assert resources.status_code == 200, resources.text
    assert resources.json()["image_projects"][0]["id"] == project.json()["id"]


def test_first_setup_wires_model_capabilities_without_api_restart(tmp_path):
    client, token, _home = make_client(tmp_path)
    response = client.post(
        "/api/v1/setup/initialize",
        headers={"X-Setup-Token": token},
        json={"parent": ".", "username": "admin", "password": "correct horse battery staple"},
    )
    assert response.status_code == 201, response.text
    app = client.app
    assert app.state.model_artifact_service is not None
    assert app.state.model_inference_service is not None
    assert app.state.model_evaluation_service is not None
    assert app.state.model_artifact_service.capabilities is app.state.capabilities
    assert app.state.model_evaluation_service.models is app.state.model_service
