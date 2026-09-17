import json

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.inference import Detection
from vision_dataset_workbench.models import InferenceModel, ModelProject, Task, User
from vision_dataset_workbench.services.model_inference import (
    ModelInferenceConflict,
    ModelInferenceForbidden,
    ModelInferenceService,
)


class FakeRunner:
    def predict(self, *_args, **_kwargs):
        return [Detection("car", 2, 3, 20, 22, 0.91)]


def setup(tmp_path):
    workspace = tmp_path / "workspace"
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    model_file = workspace / "models" / "model-id" / "best.pt"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"weights")
    with Session(engine) as database:
        owner = User(id="owner", username="owner", username_normalized="owner", password_hash="x")
        viewer = User(id="viewer", username="viewer", username_normalized="viewer", password_hash="x")
        database.add_all([owner, viewer])
        database.flush()
        database.add(ModelProject(id="project", name="Models", name_normalized="models", series_type="archive", created_by_id=owner.id))
        database.flush()
        database.add(InferenceModel(id="model-id", model_project_id="project", model_code="detector", name="Detector", kind="yolo", status="ready", storage_path="models/model-id/best.pt", sha256="a" * 64, source_name="best.pt", created_by_id=owner.id))
        database.commit()
        owner = database.get(User, "owner")
        viewer = database.get(User, "viewer")
        database.expunge(owner)
        database.expunge(viewer)
    return engine, workspace, ModelInferenceService(engine, workspace, FakeRunner()), owner, viewer


def upload_image(tmp_path, name="upload.jpg"):
    path = tmp_path / name
    Image.new("RGB", (32, 32), "white").save(path)
    return path


def test_image_session_is_persistent_replaceable_downloadable_and_saveable(tmp_path):
    engine, workspace, service, owner, viewer = setup(tmp_path)
    run = service.create(owner, "model-id", "image", "pt", upload_image(tmp_path), "car.jpg", {}, replace=False)
    assert run.status == "succeeded"
    assert json.loads(run.statistics)["detections"] == 1
    assert service.file(owner, run.id, "result")[0].is_file()
    assert service.current(owner, "model-id").id == run.id
    with pytest.raises(ModelInferenceConflict):
        service.create(owner, "model-id", "image", "pt", upload_image(tmp_path, "second.jpg"), "second.jpg", {}, replace=False)
    with pytest.raises(ModelInferenceForbidden):
        service.save(viewer, run.id)
    saved = service.save(owner, run.id)
    assert saved.saved_at is not None and saved.expires_at is None
    replacement = service.create(owner, "model-id", "image", "pt", upload_image(tmp_path, "third.jpg"), "third.jpg", {"image_size": 672}, replace=False)
    assert json.loads(replacement.parameters)["image_size"] == 672
    assert (workspace / replacement.result_path).is_file()
    engine.dispose()


def test_video_session_creates_worker_task_and_delete_cancels_it(tmp_path):
    engine, _workspace, service, owner, _viewer = setup(tmp_path)
    video = tmp_path / "video.mp4"
    video.write_bytes(b"not-yet-probed")
    run = service.create(owner, "model-id", "video", "pt", video, "video.mp4", {"stride": 3}, replace=False)
    assert run.status == "queued" and run.task_id
    service.delete(owner, run.id)
    with service._session_factory() as database:
        task = database.get(Task, run.task_id)
        assert task.status == "canceled" and task.cancel_requested is True
    assert service.current(owner, "model-id") is None
    engine.dispose()
