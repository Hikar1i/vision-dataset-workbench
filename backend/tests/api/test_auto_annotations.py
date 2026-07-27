from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.capabilities import (
    CapabilityStatus,
    FeatureCapabilities,
    GpuStatus,
    SystemCapabilities,
)
from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.inference import Detection
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import (
    Frame,
    InferenceModel,
    ProjectLabel,
    SamplingPlan,
    User,
    Video,
)
from vision_dataset_workbench.security.passwords import hash_password

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


class FakeRunner:
    def predict(self, *_args, **_kwargs):
        return [
            Detection("helmet", 10, 20, 110, 220, 0.91),
            Detection("dog", 200, 100, 420, 500, 0.82),
        ]


def capabilities():
    ready = CapabilityStatus(True)
    return SystemCapabilities(
        gpu=GpuStatus(True, None, ()),
        pytorch_cuda=ready,
        onnx_cuda=CapabilityStatus(False, "unused"),
        features=FeatureCapabilities(ready, ready, ready, ready),
    )


def make_app(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects" / "project-id" / "frames" / "video-id").mkdir(parents=True)
    model_path = workspace / "models" / "model-id" / "model.pt"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"weights")
    frame_path = workspace / "projects" / "project-id" / "frames" / "video-id" / "000001.jpg"
    frame_path.write_bytes(b"image")
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    password_hash = hash_password(PASSWORD)
    with Session(engine) as session:
        session.add_all(
            [
                User(id="owner-id", username="owner", username_normalized="owner", password_hash=password_hash, status="active"),
                User(id="viewer-id", username="viewer", username_normalized="viewer", password_hash=password_hash, status="active"),
            ]
        )
        session.flush()
        from vision_dataset_workbench.models import Project, ProjectMembership
        session.add(Project(id="project-id", name="project", creator_id="owner-id"))
        session.add(ProjectMembership(project_id="project-id", user_id="viewer-id", role="viewer"))
        session.flush()
        session.add(Video(id="video-id", project_id="project-id", source_type="local", title="video", status="ready", width=1920, height=1080))
        session.add(InferenceModel(id="model-id", name="YOLO", kind="yolo", status="ready", storage_path="models/model-id/model.pt", source_name="model.pt", created_by_id="owner-id"))
        session.flush()
        session.add(SamplingPlan(id="plan-id", video_id="video-id", mode="target_frames", parameters="{}", output_format="jpg", output_quality=2, expected_frames=1, extracted_frames=1, enabled_frames=1))
        session.add(Frame(id="frame-id", video_id="video-id", generation=1, sequence=1, source_frame_index=0, time_offset=0, file_path=frame_path.relative_to(workspace).as_posix()))
        session.add(ProjectLabel(id="helmet-label", project_id="project-id", name="helmet", name_normalized="helmet", color="#16866f", sort_order=0, enabled=True))
        session.commit()
    engine.dispose()
    app = create_app(RuntimeSettings(home=home, workspace=workspace), capabilities=capabilities())
    app.state.auto_annotation_service.runner = FakeRunner()
    return app


def client_for(app, username):
    client = TestClient(app)
    assert client.post("/api/v1/auth/login", headers=ORIGIN, json={"username": username, "password": PASSWORD}).status_code == 200
    return client


def url():
    return "/api/v1/projects/project-id/videos/video-id/frames/frame-id/auto-annotations"


def test_single_inference_returns_draft_and_creates_only_detected_missing_labels(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "owner")
    response = owner.post(url(), headers=ORIGIN, json={"model_id": "model-id", "categories": ["helmet", "dog", "car"], "confidence": 0.25, "iou": 0.45})

    assert response.status_code == 200
    body = response.json()
    assert [item["label_name"] for item in body["items"]] == ["helmet", "dog"]
    assert [label["name"] for label in body["created_labels"]] == ["dog"]
    assert owner.get("/api/v1/projects/project-id/videos/video-id/frames/frame-id/annotations").json()["items"] == []
    with Session(app.state.auth_service.engine) as session:
        assert session.query(ProjectLabel).filter_by(project_id="project-id").count() == 2


def test_single_inference_rejects_viewer_and_requires_same_origin(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "owner")
    viewer = client_for(app, "viewer")
    payload = {"model_id": "model-id", "categories": [], "confidence": 0.25, "iou": 0.45}

    assert viewer.post(url(), headers=ORIGIN, json=payload).status_code == 403
    assert owner.post(url(), json=payload).status_code == 403
