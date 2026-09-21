import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm import Session, sessionmaker

from vision_dataset_workbench.capabilities import (
    CapabilityStatus,
    FeatureCapabilities,
    GpuDevice,
    GpuStatus,
    SystemCapabilities,
)
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.models import (
    InferenceModel,
    ModelArtifact,
    ModelProject,
    ModelProjectMembership,
    Task,
    User,
)
from vision_dataset_workbench.model_artifact_task import execute_model_conversion
from vision_dataset_workbench.services.gpu_leases import GpuLeaseService
from vision_dataset_workbench.services.model_artifacts import (
    InvalidModelArtifact,
    ModelArtifactConflict,
    ModelArtifactForbidden,
    ModelArtifactService,
)
from vision_dataset_workbench.services.models import ModelService
from vision_dataset_workbench.services.projects import ProjectService


def ready_capabilities():
    yes = CapabilityStatus(True)
    return SystemCapabilities(
        gpu=GpuStatus(True, None, (GpuDevice(0, "A4000", 16000, "GPU-a", "8.6"),)),
        pytorch_cuda=yes,
        features=FeatureCapabilities(yes, yes, yes, yes, yes, yes),
    )


def setup_service(tmp_path):
    workspace = tmp_path / "workspace"
    database_path = workspace / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    source = workspace / "models" / "model-id" / "best.pt"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"weights")
    with Session(engine) as database:
        database.add_all(
            [
                User(
                    id="owner",
                    username="owner",
                    username_normalized="owner",
                    password_hash="hash",
                ),
                User(
                    id="viewer",
                    username="viewer",
                    username_normalized="viewer",
                    password_hash="hash",
                ),
            ]
        )
        database.flush()
        database.add(
            ModelProject(
                id="project-id",
                name="project",
                name_normalized="project",
                series_type="archive",
                created_by_id="owner",
            )
        )
        database.flush()
        database.add(
            ModelProjectMembership(
                model_project_id="project-id", user_id="viewer", role="viewer"
            )
        )
        database.add(
            InferenceModel(
                id="model-id",
                model_project_id="project-id",
                name="model",
                model_code="model",
                kind="yolo",
                status="ready",
                storage_path="models/model-id/best.pt",
                sha256="a" * 64,
                source_name="best.pt",
                created_by_id="owner",
            )
        )
        database.commit()
        owner = database.get(User, "owner")
        viewer = database.get(User, "viewer")
        database.expunge(owner)
        database.expunge(viewer)
    settings = RuntimeSettings(home=tmp_path, workspace=workspace)
    projects = ProjectService(engine, settings, workspace)
    models = ModelService(engine, settings, workspace, projects)
    service = ModelArtifactService(
        engine,
        workspace,
        ready_capabilities(),
        models,
        fingerprint=lambda: {"tensorrt": "11.3.0", "cuda_runtime": "12.8.1"},
    )
    return engine, service, owner, viewer


def test_create_freezes_supported_export_configuration_and_permissions(tmp_path):
    engine, service, owner, viewer = setup_service(tmp_path)

    onnx, task = service.create(owner, "model-id", "onnx", image_size=672, dynamic=True)
    config = json.loads(onnx.export_config)
    assert config == {
        "imgsz": 672,
        "batch": 1,
        "dynamic": True,
        "simplify": True,
        "nms": False,
        "precision": None,
    }
    assert task.type == "convert_model"
    assert json.loads(task.payload)["source_model_sha256"] == "a" * 64
    with pytest.raises(ModelArtifactConflict):
        service.create(owner, "model-id", "onnx")
    with pytest.raises(ModelArtifactForbidden):
        service.create(viewer, "model-id", "engine")
    with pytest.raises(InvalidModelArtifact):
        service.create(owner, "model-id", "engine", dynamic=True)
    engine.dispose()


def test_source_and_strict_tensorrt_environment_changes_mark_artifacts_stale(tmp_path):
    engine, service, owner, _viewer = setup_service(tmp_path)
    artifact, _task = service.create(owner, "model-id", "engine")
    target = service.workspace / "models" / "model-id" / "artifacts" / "model.engine"
    target.parent.mkdir()
    target.write_bytes(b"engine")
    with service._session_factory() as database:
        stored = database.get(ModelArtifact, artifact.id)
        stored.status = "ready"
        stored.storage_path = target.relative_to(service.workspace).as_posix()
        stored.sha256 = "b" * 64
        stored.gpu_uuid = "GPU-a"
        stored.environment_fingerprint = json.dumps(
            {
                "gpu_uuid": "GPU-a",
                "compute_capability": "8.6",
                "tensorrt": "11.3.0",
                "cuda_runtime": "12.8.0",
            }
        )
        database.commit()

    assert service.downloadable(owner, artifact.id)[1] == target
    service._fingerprint = lambda: {"tensorrt": "11.3.1", "cuda_runtime": "12.8"}
    with pytest.raises(ModelArtifactConflict):
        service.downloadable(owner, artifact.id)
    assert service.list(owner, "model-id")[0].status == "stale"
    engine.dispose()


def test_source_hash_change_invalidates_ready_onnx(tmp_path):
    engine, service, owner, _viewer = setup_service(tmp_path)
    artifact, _task = service.create(owner, "model-id", "onnx")
    with service._session_factory() as database:
        stored = database.get(ModelArtifact, artifact.id)
        stored.status = "ready"
        model = database.get(InferenceModel, "model-id")
        model.sha256 = "c" * 64
        database.commit()

    assert service.list(owner, "model-id")[0].status == "stale"
    engine.dispose()


def test_conversion_worker_atomically_publishes_validated_onnx(tmp_path, monkeypatch):
    engine, service, owner, _viewer = setup_service(tmp_path)
    artifact, task = service.create(owner, "model-id", "onnx")
    with service._session_factory() as database:
        stored_task = database.get(Task, task.id)
        stored_task.status = "running"
        database.commit()
    task_temp = service.workspace / "tmp" / task.id
    task_temp.mkdir(parents=True)

    class FakeYolo:
        def __init__(self, source):
            self.source = Path(source)

        def export(self, **_arguments):
            output = self.source.with_suffix(".onnx")
            output.write_bytes(b"valid-onnx")
            return output

    import vision_dataset_workbench.model_artifact_task as executor

    monkeypatch.setattr(
        executor.importlib,
        "import_module",
        lambda name: SimpleNamespace(YOLO=FakeYolo) if name == "ultralytics" else None,
    )
    monkeypatch.setattr(executor, "_validate_export", lambda _path, _format: None)
    execute_model_conversion(
        sessionmaker(engine, expire_on_commit=False),
        service.workspace,
        task.id,
        task_temp,
        datetime.now,
        lambda _task_id, _progress: None,
        GpuLeaseService(engine, devices=()),
    )

    with service._session_factory() as database:
        stored = database.get(ModelArtifact, artifact.id)
        stored_task = database.get(Task, task.id)
        assert stored.status == "ready"
        assert (service.workspace / stored.storage_path).read_bytes() == b"valid-onnx"
        assert stored_task.status == "succeeded"
    engine.dispose()
