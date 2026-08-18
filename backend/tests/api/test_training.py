import time
from fastapi.testclient import TestClient
from sqlalchemy import select
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
    TrainingRun,
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
    (dataset_dir / "train" / "images").mkdir(parents=True)
    (dataset_dir / "train" / "labels").mkdir(parents=True)
    (dataset_dir / "val" / "images").mkdir(parents=True)
    (dataset_dir / "val" / "labels").mkdir(parents=True)
    (dataset_dir / "train" / "images" / "frame.jpg").write_bytes(b"image")
    (dataset_dir / "train" / "labels" / "frame.txt").write_text("0 0.5 0.5 0.2 0.2\n")
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
                total_frames=1,
                train_frames=1,
                storage_path="exports/dataset",
                manifest=(
                    '{"total_frames":1,"train_frames":1,"val_frames":0,'
                    '"labels":[{"name":"fire","mapping":0,"enabled":true}]}'
                ),
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
                {
                    "name": "small",
                    "template_id": "00000000-0000-0000-0000-000000000002",
                    "epochs_override": 2,
                    "gpu_index": 0,
                    "queue_order": 1,
                },
                {
                    "name": "small-alt",
                    "template_id": "00000000-0000-0000-0000-000000000002",
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
                    "template_id": "00000000-0000-0000-0000-000000000002",
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


def test_resources_code_availability_and_multi_dataset_draft_round_trip(tmp_path, monkeypatch):
    _, client, _ = setup_app(tmp_path, monkeypatch)
    resources = client.get("/api/v1/training/resources").json()
    assert resources["datasets"][0] == {
        "id": "export-id",
        "name": "Fire v1",
        "project_id": "project-id",
        "project_name": "Fire dataset",
        "total_frames": 1,
        "train_frames": 1,
        "val_frames": 0,
        "labels": [{"index": 0, "name": "fire"}],
    }
    assert (
        client.get(
            "/api/v1/training-tasks/code-availability", params={"code": "multi-fire"}
        ).json()["available"]
        is True
    )
    payload = {
        "code": "multi-fire",
        "name": "Multi fire",
        "mode": "single_model",
        "default_dataset_mode": "multi",
        "default_multi_dataset_config": {
            "version": 1,
            "dataset_export_ids": ["export-id"],
            "target_classes": ["fire"],
        },
        "default_template_id": "00000000-0000-0000-0000-000000000002",
        "default_base_model_id": "base-model",
        "models": [{"name": "one", "dataset_mode": "inherit"}],
    }
    created = client.post("/api/v1/training-tasks", headers=ORIGIN, json=payload)
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["default_dataset_mode"] == "multi"
    assert body["default_multi_dataset_config"] == payload["default_multi_dataset_config"]
    assert body["models"][0]["dataset_mode"] == "inherit"
    assert client.get(
        "/api/v1/training-tasks/code-availability", params={"code": "multi-fire"}
    ).json() == {"code": "multi-fire", "available": False, "reason": "编码已存在"}


def test_template_changes_rebase_drafts_and_started_snapshots_stay_frozen(tmp_path, monkeypatch):
    _, client, _ = setup_app(tmp_path, monkeypatch)
    template = client.post(
        "/api/v1/hyperparameter-templates",
        headers=ORIGIN,
        json={
            "name": "Draft base",
            "epochs": 10,
            "batch_mode": "auto",
            "batch_value": None,
            "image_size": 640,
            "extra_parameters": {"lr0": 0.01, "patience": 50},
        },
    ).json()
    resources_template = next(
        item
        for item in client.get("/api/v1/training/resources").json()["templates"]
        if item["id"] == template["id"]
    )
    assert resources_template["version"] == 1
    assert resources_template["effective_parameters"]["lr0"] == 0.01

    payload = {
        "code": "override-draft",
        "name": "Override draft",
        "mode": "custom_sequence",
        "default_dataset_export_id": "export-id",
        "default_template_id": template["id"],
        "default_base_model_id": "base-model",
        "default_epochs_override": 20,
        "default_extra_parameters_override": {
            "version": 1,
            "set": {"lr0": 0.02},
            "remove": ["patience"],
        },
        "models": [
            {
                "name": "inherit",
                "epochs_override": 99,
                "extra_parameters_override": {
                    "version": 1,
                    "set": {"mosaic": 0.5},
                    "remove": [],
                },
                "gpu_index": 0,
                "queue_order": 1,
            },
            {
                "name": "explicit",
                "template_id": template["id"],
                "image_size_override": 960,
                "extra_parameters_override": {
                    "version": 1,
                    "set": {"mosaic": 0.5},
                    "remove": ["lr0"],
                },
                "gpu_index": 0,
                "queue_order": 2,
            },
        ],
    }
    draft = client.post("/api/v1/training-tasks", headers=ORIGIN, json=payload)
    assert draft.status_code == 201, draft.text
    draft_body = draft.json()
    assert draft_body["default_epochs_override"] == 20
    assert draft_body["models"][1]["extra_parameters_override"]["remove"] == ["lr0"]

    derived = client.post(
        f"/api/v1/training-tasks/{draft_body['id']}/derive",
        headers={**ORIGIN, "Idempotency-Key": "derive-overrides"},
        json={"task_code": "override-derived", "task_name": "Derived"},
    )
    assert derived.status_code == 201, derived.text
    assert derived.json()["default_epochs_override"] == 20
    assert derived.json()["models"][1]["extra_parameters_override"]["remove"] == ["lr0"]

    update_payload = {
        "version": template["version"],
        "name": template["name"],
        "description": "updated before start",
        "epochs": 30,
        "batch_mode": "auto",
        "batch_value": None,
        "image_size": 640,
        "extra_parameters": {"lr0": 0.03, "patience": 60},
    }
    updated_template = client.patch(
        f"/api/v1/hyperparameter-templates/{template['id']}",
        headers=ORIGIN,
        json=update_payload,
    ).json()
    started = client.post(f"/api/v1/training-tasks/{draft_body['id']}/start", headers=ORIGIN)
    assert started.status_code == 200, started.text
    inherit_snapshot = started.json()["models"][0]["template_snapshot"]
    explicit_snapshot = started.json()["models"][1]["template_snapshot"]
    assert inherit_snapshot["version"] == 2
    assert inherit_snapshot["parameters"] == {
        "epochs": 20,
        "batch": -1,
        "imgsz": 640,
        "lr0": 0.02,
    }
    assert explicit_snapshot["parameters"] == {
        "epochs": 30,
        "batch": -1,
        "imgsz": 960,
        "patience": 60,
        "mosaic": 0.5,
    }

    client.patch(
        f"/api/v1/hyperparameter-templates/{template['id']}",
        headers=ORIGIN,
        json={**update_payload, "version": updated_template["version"], "epochs": 40},
    )
    detail = client.get(f"/api/v1/training-tasks/{draft_body['id']}").json()
    assert detail["models"][0]["template_snapshot"] == inherit_snapshot


def test_invalid_multi_dataset_config_is_rejected(tmp_path, monkeypatch):
    _, client, _ = setup_app(tmp_path, monkeypatch)
    response = client.post(
        "/api/v1/training-tasks",
        headers=ORIGIN,
        json={
            "code": "invalid-multi",
            "name": "Invalid multi",
            "default_dataset_mode": "multi",
            "default_multi_dataset_config": {
                "version": 1,
                "dataset_export_ids": ["export-id"],
                "target_classes": ["missing"],
            },
            "models": [{"name": "one"}],
        },
    )
    assert response.status_code == 422
    assert "target classes are unavailable" in response.text


def test_multi_dataset_start_prepares_before_queue_and_reuses_same_task_hash(tmp_path, monkeypatch):
    app, client, workspace = setup_app(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/training-tasks",
        headers=ORIGIN,
        json={
            "code": "prepared-fire",
            "name": "Prepared fire",
            "mode": "custom_sequence",
            "default_dataset_mode": "multi",
            "default_multi_dataset_config": {
                "version": 1,
                "dataset_export_ids": ["export-id"],
                "target_classes": ["fire"],
            },
            "default_template_id": "00000000-0000-0000-0000-000000000002",
            "default_epochs_override": 1,
            "default_base_model_id": "base-model",
            "models": [
                {"name": "one", "gpu_index": 0, "queue_order": 1},
                {"name": "two", "gpu_index": 1, "queue_order": 1},
            ],
        },
    ).json()
    started = client.post(f"/api/v1/training-tasks/{created['id']}/start", headers=ORIGIN)
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "preparing"
    assert started.json()["preparation"]["status"] == "queued"
    assert all(not model["runs"] for model in started.json()["models"])

    scheduler = TrainingScheduler(
        app.state.auth_service.engine, workspace, worker_id="prepare-worker", fake=True
    )
    scheduler._start_preparations()
    with Session(app.state.auth_service.engine) as db:
        assert list(db.scalars(select(TrainingRun))) == []

    for _ in range(300):
        scheduler.tick()
        detail = client.get(f"/api/v1/training-tasks/{created['id']}").json()
        if detail["status"] == "succeeded":
            break
        time.sleep(0.02)
    assert detail["status"] == "succeeded", detail
    paths = {model["dataset_snapshot"]["prepared_storage_path"] for model in detail["models"]}
    assert len(paths) == 1
    prepared = workspace / paths.pop()
    assert (prepared / "READY").is_file()
    assert (prepared / "train/labels/export-id_frame.txt").read_text() == ("0 0.5 0.5 0.2 0.2\n")
    assert detail["preparation"]["artifacts"] == [
        {
            "config_hash": prepared.name,
            "dataset_count": 1,
            "images": 1,
            "annotations": 1,
            "ignored_annotations": 0,
            "negative_images": 0,
        }
    ]
    log = client.get(f"/api/v1/training-tasks/{created['id']}/preparation-log").json()
    assert "[prepare] completed" in log["content"]


def test_preparation_failure_can_retry_and_queued_preparation_can_cancel(tmp_path, monkeypatch):
    app, client, workspace = setup_app(tmp_path, monkeypatch)

    def create(code):
        return client.post(
            "/api/v1/training-tasks",
            headers=ORIGIN,
            json={
                "code": code,
                "name": code,
                "default_dataset_mode": "multi",
                "default_multi_dataset_config": {
                    "version": 1,
                    "dataset_export_ids": ["export-id"],
                    "target_classes": ["fire"],
                },
                "default_template_id": "00000000-0000-0000-0000-000000000002",
                "default_epochs_override": 1,
                "default_base_model_id": "base-model",
                "models": [{"name": "one"}],
            },
        ).json()

    canceled_source = create("cancel-prep")
    client.post(f"/api/v1/training-tasks/{canceled_source['id']}/start", headers=ORIGIN)
    canceled = client.post(f"/api/v1/training-tasks/{canceled_source['id']}/cancel", headers=ORIGIN)
    assert canceled.json()["status"] == "canceled"
    assert canceled.json()["preparation"]["status"] == "canceled"

    source = create("retry-prep")
    client.post(f"/api/v1/training-tasks/{source['id']}/start", headers=ORIGIN)
    label = workspace / "exports/dataset/train/labels/frame.txt"
    label.unlink()
    scheduler = TrainingScheduler(
        app.state.auth_service.engine, workspace, worker_id="retry-worker", fake=True
    )
    for _ in range(200):
        scheduler.tick()
        detail = client.get(f"/api/v1/training-tasks/{source['id']}").json()
        if detail["status"] == "preparation_failed":
            break
        time.sleep(0.02)
    assert detail["status"] == "preparation_failed", detail
    assert detail["preparation"]["error"]
    assert not any(model["runs"] for model in detail["models"])

    label.write_text("0 0.5 0.5 0.2 0.2\n")
    retried = client.post(
        f"/api/v1/training-tasks/{source['id']}/retry-preparation", headers=ORIGIN
    )
    assert retried.status_code == 200, retried.text
    for _ in range(300):
        scheduler.tick()
        detail = client.get(f"/api/v1/training-tasks/{source['id']}").json()
        if detail["status"] == "succeeded":
            break
        time.sleep(0.02)
    assert detail["status"] == "succeeded", detail


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
            "default_epochs_override": 20,
            "default_base_model_id": "base-model",
            "models": [
                {"name": "first", "gpu_index": 0, "queue_order": 1},
                {"name": "second", "gpu_index": 0, "queue_order": 2},
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
