import json
from datetime import datetime

import pytest
from PIL import Image
from sqlalchemy.orm import Session

from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.inference import Detection
from vision_dataset_workbench.model_inference_task import _draw_video_detection
from vision_dataset_workbench.models import (
    InferenceModel,
    ModelProject,
    ModelProjectMembership,
    Task,
    User,
)
from vision_dataset_workbench.services.model_inference import (
    ModelInferenceConflict,
    ModelInferenceForbidden,
    ModelInferenceService,
)
from vision_dataset_workbench.services.models import ModelService
from vision_dataset_workbench.services.projects import ProjectService


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
        database.add(
            ModelProjectMembership(
                model_project_id="project", user_id="viewer", role="viewer"
            )
        )
        database.add(InferenceModel(id="model-id", model_project_id="project", model_code="detector", name="Detector", kind="yolo", status="ready", storage_path="models/model-id/best.pt", sha256="a" * 64, source_name="best.pt", created_by_id=owner.id))
        database.commit()
        owner = database.get(User, "owner")
        viewer = database.get(User, "viewer")
        database.expunge(owner)
        database.expunge(viewer)
    settings = RuntimeSettings(home=tmp_path, workspace=workspace)
    projects = ProjectService(engine, settings, workspace)
    models = ModelService(engine, settings, workspace, projects)
    return (
        engine,
        workspace,
        ModelInferenceService(engine, workspace, FakeRunner(), models),
        owner,
        viewer,
    )


def upload_image(tmp_path, name="upload.jpg"):
    path = tmp_path / name
    Image.new("RGB", (32, 32), "white").save(path)
    return path


def test_image_session_is_persistent_replaceable_downloadable_and_saveable(tmp_path):
    engine, workspace, service, owner, viewer = setup(tmp_path)
    old = datetime(2025, 1, 1)
    with Session(engine) as database:
        project = database.get(ModelProject, "project")
        project.updated_at = old
        version = project.version
        database.commit()
    run = service.create(owner, "model-id", "image", "pt", upload_image(tmp_path), "car.jpg", {}, replace=False)
    assert run.status == "succeeded"
    assert json.loads(run.statistics)["detections"] == 1
    assert service.file(owner, run.id, "result")[0].is_file()
    with Image.open(workspace / run.result_path) as result:
        label_pixels = [
            result.getpixel((x, y))
            for x in range(2, 30)
            for y in range(0, 16)
        ]
    assert sum(red < 100 and green > 100 and blue > 120 for red, green, blue in label_pixels) > 100
    assert service.current(owner, "model-id").id == run.id
    with pytest.raises(ModelInferenceConflict):
        service.create(owner, "model-id", "image", "pt", upload_image(tmp_path, "second.jpg"), "second.jpg", {}, replace=False)
    with pytest.raises(ModelInferenceForbidden):
        service.save(viewer, run.id)
    with Session(engine) as database:
        assert database.get(ModelProject, "project").updated_at == old
    saved = service.save(owner, run.id)
    assert saved.saved_at is not None and saved.expires_at is None
    with Session(engine) as database:
        project = database.get(ModelProject, "project")
        assert project.updated_at > old
        assert project.version == version
    replacement = service.create(owner, "model-id", "image", "pt", upload_image(tmp_path, "third.jpg"), "third.jpg", {"image_size": 672}, replace=False)
    assert json.loads(replacement.parameters)["image_size"] == 672
    assert (workspace / replacement.result_path).is_file()
    engine.dispose()


def test_video_detection_uses_matching_box_and_label_background_colors():
    class FakeCv2:
        FONT_HERSHEY_SIMPLEX = 0
        LINE_AA = 16
        FILLED = -1

        def __init__(self):
            self.rectangles = []

        def rectangle(self, *_arguments):
            self.rectangles.append(_arguments)

        @staticmethod
        def getTextSize(*_arguments):
            return (96, 16), 4

        @staticmethod
        def putText(*_arguments):
            return None

    cv2 = FakeCv2()
    _draw_video_detection(cv2, object(), Detection("car", 20, 30, 80, 90, 0.91))

    assert len(cv2.rectangles) == 2
    assert cv2.rectangles[0][3] == cv2.rectangles[1][3]
    assert cv2.rectangles[1][4] == cv2.FILLED


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
