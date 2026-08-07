from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import User
from vision_dataset_workbench.security.passwords import hash_password

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


def test_llm_config_create_masks_and_retains_api_key(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    database_path = workspace / "db/workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    with Session(engine) as database:
        database.add(
            User(
                id="owner-id",
                username="owner",
                username_normalized="owner",
                password_hash=hash_password(PASSWORD),
                status="active",
            )
        )
        database.commit()
    engine.dispose()
    app = create_app(RuntimeSettings(home=home, workspace=workspace))
    client = TestClient(app)
    assert client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": "owner", "password": PASSWORD},
    ).status_code == 200
    payload = {
        "name": "local vision",
        "description": "",
        "base_url": "http://localhost:8444/v1",
        "api_type": "openai",
        "model_name": "vision-model",
        "api_key": "sk-test-1234567890abcd",
        "enabled": True,
        "advanced_options": {},
    }

    created = client.post("/api/v1/me/llm-configs", headers=ORIGIN, json=payload)

    assert created.status_code == 201, created.text
    body = created.json()
    assert body["masked_api_key"] == "sk-test-******abcd"
    assert body["version"] == 1

    updated = client.patch(
        f"/api/v1/me/llm-configs/{body['id']}",
        headers=ORIGIN,
        json={**payload, "name": "renamed", "api_key": None},
    )

    assert updated.status_code == 200, updated.text
    assert updated.json()["masked_api_key"] == body["masked_api_key"]
    assert updated.json()["version"] == 2
