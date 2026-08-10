from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import User
from vision_dataset_workbench.security.passwords import hash_password

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


def make_client(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    home.mkdir()
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    with Session(engine) as session:
        session.add(User(
            id="user-id", username="user", username_normalized="user",
            password_hash=hash_password(PASSWORD), status="active",
        ))
        session.commit()
    engine.dispose()
    client = TestClient(create_app(RuntimeSettings(home=home, workspace=workspace)))
    assert client.post(
        "/api/v1/auth/login", headers=ORIGIN,
        json={"username": "user", "password": PASSWORD},
    ).status_code == 200
    return client


def test_templates_are_immutable_derivable_and_logically_deleted(tmp_path):
    client = make_client(tmp_path)
    templates = client.get("/api/v1/hyperparameter-templates").json()
    system = templates[0]
    assert system["system_key"] == "ultralytics-detect-default"
    assert system["effective_parameters"] == {"epochs": 100, "batch": -1, "imgsz": 640}
    assert client.delete(
        f"/api/v1/hyperparameter-templates/{system['id']}", headers=ORIGIN
    ).status_code == 403

    created = client.post(
        "/api/v1/hyperparameter-templates",
        headers=ORIGIN,
        json={
            "name": "Fire baseline", "description": "", "epochs": 200,
            "batch_mode": "fixed", "batch_value": 16, "image_size": 640,
            "extra_parameters": {"lr0": 0.01}, "derived_from_id": system["id"],
        },
    )
    assert created.status_code == 201
    item = created.json()
    assert item["derived_from_id"] == system["id"]
    assert client.patch(f"/api/v1/hyperparameter-templates/{item['id']}").status_code == 405
    assert client.delete(
        f"/api/v1/hyperparameter-templates/{item['id']}", headers=ORIGIN
    ).status_code == 204
    assert client.get(f"/api/v1/hyperparameter-templates/{item['id']}").status_code == 404


def test_raw_validation_returns_all_or_nothing(tmp_path):
    client = make_client(tmp_path)
    valid = client.post(
        "/api/v1/hyperparameter-templates/validate-raw",
        json={"raw": "epochs: 10\nbatch: -1\nimgsz: 640\nlr0: 0.01\n"},
    )
    assert valid.status_code == 200
    assert valid.json()["valid"] is True
    assert valid.json()["normalized"]["extra_parameters"] == {"lr0": 0.01}

    invalid = client.post(
        "/api/v1/hyperparameter-templates/validate-raw",
        json={"raw": "epochs: 10\nbatch: -1\nimgsz: 641\ndevice: 0\n"},
    ).json()
    assert invalid["valid"] is False
    assert invalid["normalized"] is None
    assert {issue["key"] for issue in invalid["issues"]} == {"imgsz", "device"}
