import time
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.capabilities import (
    CapabilityStatus,
    FeatureCapabilities,
    GpuDevice,
    GpuStatus,
    SystemCapabilities,
)
from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import (
    DatasetExport,
    InferenceModel,
    ModelProject,
    Project,
    User,
)
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.training.scheduler import TrainingScheduler

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


def capabilities():
    yes = CapabilityStatus(True)
    return SystemCapabilities(
        gpu=GpuStatus(True, None, (GpuDevice(0, "GPU 0", 16000), GpuDevice(1, "GPU 1", 8000))),
        pytorch_cuda=yes,
        features=FeatureCapabilities(yes, yes, yes),
    )


def setup_app(tmp_path, monkeypatch):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    home.mkdir()
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    dataset_dir = workspace / "exports" / "dataset"
    dataset_dir.mkdir(parents=True)
    (dataset_dir / "dataset.yaml").write_text(
        "path: .\ntrain: train/images\nval: val/images\nnames: [fire]\n"
    )
    model_path = workspace / "models" / "base.pt"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"fake-base")
    with Session(engine) as db:
        user = User(
            id="user-id",
            username="user",
            username_normalized="user",
            password_hash=hash_password(PASSWORD),
            status="active",
        )
        project = Project(id="project-id", name="Fire dataset", creator_id=user.id)
        model_project = ModelProject(
            id="base-project",
            name="YOLO11",
            name_normalized="yolo11",
            description="",
            series_type="archive",
            created_by_id=user.id,
        )
        db.add(user)
        db.flush()
        db.add_all([project, model_project])
        db.flush()
        db.add(
            DatasetExport(
                id="export-id",
                project_id=project.id,
                created_by_id=user.id,
                name="Fire v1",
                status="ready",
                train_ratio=0.8,
                storage_path="exports/dataset",
                manifest='{"labels":[{"name":"fire"}]}',
            )
        )
        db.add(
            InferenceModel(
                id="base-model",
                model_project_id=model_project.id,
                name="YOLO11s",
                model_code="yolo11s",
                kind="yolo",
                description="",
                parameters="{}",
                status="ready",
                storage_path="models/base.pt",
                file_size=9,
                sha256="a" * 64,
                source_name="base.pt",
                created_by_id=user.id,
            )
        )
        db.commit()
    engine.dispose()
    monkeypatch.setattr(
        "vision_dataset_workbench.api.training.training_telemetry",
        lambda: {
            "available": True,
            "reason": None,
            "devices": [{"index": 0}, {"index": 1}],
            "host": {},
        },
    )
    app = create_app(RuntimeSettings(home=home, workspace=workspace), capabilities=capabilities())
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/login", headers=ORIGIN, json={"username": "user", "password": PASSWORD}
        ).status_code
        == 200
    )
    return app, client, workspace


def test_custom_gpu_training_runs_publish_models_and_metrics(tmp_path, monkeypatch):
    app, client, workspace = setup_app(tmp_path, monkeypatch)
    resources = client.get("/api/v1/training/resources").json()
    assert resources["datasets"][0]["project_id"] == "project-id"
    assert resources["base_models"][0]["project_id"] == "base-project"
    created = client.post(
        "/api/v1/training-tasks",
        headers=ORIGIN,
        json={
            "code": "firedet",
            "name": "Fire detection",
            "description": "",
            "mode": "custom_sequence",
            "default_dataset_export_id": "export-id",
            "default_template_id": "00000000-0000-0000-0000-000000000002",
            "default_base_model_id": "base-model",
            "models": [
                {"name": "small", "epochs_override": 2, "gpu_index": 0, "queue_order": 1},
                {
                    "name": "small-alt",
                    "epochs_override": 2,
                    "batch_mode_override": "fixed",
                    "batch_value_override": 12.0,
                    "gpu_index": 1,
                    "queue_order": 1,
                },
            ],
        },
    )
    assert created.status_code == 201, created.text
    task_id = created.json()["id"]
    assert created.json()["actions"]["start"]["allowed"] is True
    started = client.post(f"/api/v1/training-tasks/{task_id}/start", headers=ORIGIN)
    assert started.status_code == 200, started.text
    assert started.json()["models"][0]["artifact_code"].startswith("firedet-")

    scheduler = TrainingScheduler(
        app.state.auth_service.engine, workspace, worker_id="test-worker", fake=True
    )
    for _ in range(200):
        scheduler.tick()
        detail = client.get(f"/api/v1/training-tasks/{task_id}").json()
        if detail["status"] == "succeeded":
            break
        time.sleep(0.02)
    assert detail["status"] == "succeeded", detail
    assert all(item["progress"] == 100 for item in detail["models"])
    run_id = detail["models"][0]["runs"][0]["id"]
    metric_rows = client.get(f"/api/v1/training-runs/{run_id}/metrics").json()
    assert len(metric_rows) == 2 and metric_rows[0]["dfl_loss"] is not None
    assert client.get(f"/api/v1/training-runs/{run_id}/pr-curve").json()["kind"] == "interactive"
    projects = client.get("/api/v1/model-projects").json()
    trained = next(item for item in projects if item["series_type"] == "training")
    assert len(client.get(f"/api/v1/model-projects/{trained['id']}/models").json()) == 2
    model_id = detail["models"][0]["id"]
    first_retry = client.post(
        f"/api/v1/training-models/{model_id}/retry",
        headers={**ORIGIN, "Idempotency-Key": "retry-success-1"},
        json={"confirm_replace": True},
    )
    second_retry = client.post(
        f"/api/v1/training-models/{model_id}/retry",
        headers={**ORIGIN, "Idempotency-Key": "retry-success-1"},
        json={"confirm_replace": True},
    )
    assert first_retry.status_code == 200
    assert second_retry.json()["id"] == first_retry.json()["id"]


def test_start_reports_resource_and_hyperparameter_errors_together(tmp_path, monkeypatch):
    _, client, _ = setup_app(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/training-tasks",
        headers=ORIGIN,
        json={
            "code": "invalid-start",
            "name": "Invalid start",
            "mode": "custom_sequence",
            "default_dataset_export_id": "export-id",
            "default_template_id": "00000000-0000-0000-0000-000000000002",
            "models": [
                {"name": "missing-base", "gpu_index": 0, "queue_order": 1},
                {
                    "name": "invalid-batch",
                    "base_model_id": "base-model",
                    "batch_mode_override": "fixed",
                    "batch_value_override": 12.5,
                    "gpu_index": 1,
                    "queue_order": 1,
                },
            ],
        },
    ).json()
    started = client.post(f"/api/v1/training-tasks/{created['id']}/start", headers=ORIGIN)
    assert started.status_code == 422
    assert "models[0].base_model is not ready" in started.text
    assert "models[1].hyperparameters.batch" in started.text


def test_same_gpu_models_are_strictly_serial_and_task_cancel_covers_queue(tmp_path, monkeypatch):
    app, client, workspace = setup_app(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/training-tasks",
        headers=ORIGIN,
        json={
            "code": "serialdet",
            "name": "Serial",
            "mode": "single_device_serial",
            "default_dataset_export_id": "export-id",
            "default_template_id": "00000000-0000-0000-0000-000000000002",
            "default_base_model_id": "base-model",
            "models": [
                {"name": "first", "epochs_override": 20, "gpu_index": 0, "queue_order": 1},
                {"name": "second", "epochs_override": 20, "gpu_index": 0, "queue_order": 2},
            ],
        },
    ).json()
    client.post(f"/api/v1/training-tasks/{created['id']}/start", headers=ORIGIN)
    scheduler = TrainingScheduler(
        app.state.auth_service.engine, workspace, worker_id="serial-worker", fake=True
    )
    scheduler.tick()
    detail = client.get(f"/api/v1/training-tasks/{created['id']}").json()
    assert [item["status"] for item in detail["models"]] == ["running", "queued"]
    canceled = client.post(f"/api/v1/training-tasks/{created['id']}/cancel", headers=ORIGIN).json()
    assert [item["status"] for item in canceled["models"]] == ["canceling", "canceled"]
    for _ in range(100):
        scheduler.tick()
        detail = client.get(f"/api/v1/training-tasks/{created['id']}").json()
        if detail["status"] == "canceled":
            break
        time.sleep(0.01)
    assert detail["status"] == "canceled"


def test_draft_code_is_immutable_and_derive_forbids_dataset_injection(tmp_path, monkeypatch):
    _, client, _ = setup_app(tmp_path, monkeypatch)
    payload = {
        "code": "baseline",
        "name": "Baseline",
        "mode": "single_model",
        "models": [
            {
                "name": "one",
                "dataset_export_id": "export-id",
                "template_id": "00000000-0000-0000-0000-000000000002",
                "base_model_id": "base-model",
                "gpu_index": 0,
                "queue_order": 1,
            }
        ],
    }
    task = client.post("/api/v1/training-tasks", headers=ORIGIN, json=payload).json()
    assert (
        client.patch(
            f"/api/v1/training-tasks/{task['id']}",
            headers=ORIGIN,
            json={**payload, "code": "changed", "version": task["version"]},
        ).status_code
        == 422
    )
    model_id = task["models"][0]["id"]
    response = client.post(
        f"/api/v1/training-models/{model_id}/derive",
        headers={**ORIGIN, "Idempotency-Key": "derive-1"},
        json={"task_code": "derived", "task_name": "Derived", "dataset_export_id": "other"},
    )
    assert response.status_code == 422
