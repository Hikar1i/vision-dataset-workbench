import json

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
    Task,
    User,
    UserXAnyLabelingSetting,
    Video,
)
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.xanylabeling import RemoteModelOption

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


class FakeRunner:
    def predict(self, *_args, **_kwargs):
        return [
            Detection("helmet", 10, 20, 110, 220, 0.91),
            Detection("dog", 200, 100, 420, 500, 0.82),
        ]


class FakeRemoteClient:
    def __init__(self, *_args):
        pass

    def list_models(self):
        return [
            RemoteModelOption(
                '["remote-detector","grounding"]',
                "remote-detector",
                "grounding",
                "Remote Detector / Grounding",
                "text_prompt",
            )
        ]

    def predict(self, *_args):
        return [Detection("dog", 200, 100, 420, 500, 0.82)]


def capabilities():
    ready = CapabilityStatus(True)
    return SystemCapabilities(
        gpu=GpuStatus(True, None, ()),
        pytorch_cuda=ready,
        features=FeatureCapabilities(ready, ready, ready),
    )


def make_app(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects" / "project-id" / "frames" / "TESTV001").mkdir(parents=True)
    model_path = workspace / "models" / "model-id" / "model.pt"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"weights")
    frame_path = (
        workspace
        / "projects"
        / "project-id"
        / "frames"
        / "TESTV001"
        / "TESTV001_frame_000001.jpg"
    )
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
        session.add(Video(id="video-id", project_id="project-id", short_code="TESTV001", source_type="local", title="video", status="ready", width=1920, height=1080))
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

    saved = owner.put(
        "/api/v1/projects/project-id/videos/video-id/frames/frame-id/annotations",
        headers=ORIGIN,
        json={
            "annotation_revision": 1,
            "items": [
                {
                    "id": body["items"][0]["id"],
                    "label_id": body["items"][0]["label_id"],
                    "x_min": 10,
                    "y_min": 20,
                    "x_max": 110,
                    "y_max": 220,
                    "source": "model",
                    "confidence": 0.91,
                }
            ],
        },
    )
    assert saved.status_code == 200
    assert owner.delete(
        f"/api/v1/projects/project-id/labels/{body['items'][0]['label_id']}",
        headers=ORIGIN,
    ).status_code == 409


def test_remote_single_and_batch_use_user_setting_and_source_payload(tmp_path):
    app = make_app(tmp_path)
    app.state.xanylabeling_settings_service.client_factory = FakeRemoteClient
    with Session(app.state.auth_service.engine) as session:
        session.add(
            UserXAnyLabelingSetting(
                user_id="owner-id", server_url="http://server.test"
            )
        )
        session.commit()
    owner = client_for(app, "owner")
    payload = {
        "source": "xanylabeling",
        "model_id": "remote-detector",
        "remote_task_id": "grounding",
        "categories": ["dog"],
        "confidence": 0.25,
        "iou": 0.45,
    }

    single = owner.post(url(), headers=ORIGIN, json=payload)
    batch = owner.post(
        "/api/v1/projects/project-id/videos/video-id/auto-annotations",
        headers=ORIGIN,
        json={**payload, "overwrite": False},
    )

    assert single.status_code == 200
    assert [item["label_name"] for item in single.json()["items"]] == ["dog"]
    assert batch.status_code == 202
    with Session(app.state.auth_service.engine) as session:
        task = session.get(Task, batch.json()["id"])
        task_payload = json.loads(task.payload)
    assert task_payload["source"] == "xanylabeling"
    assert task_payload["remote_task_id"] == "grounding"


def test_single_inference_rejects_viewer_and_requires_same_origin(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "owner")
    viewer = client_for(app, "viewer")
    payload = {"model_id": "model-id", "categories": [], "confidence": 0.25, "iou": 0.45}

    assert viewer.post(url(), headers=ORIGIN, json=payload).status_code == 403
    assert owner.post(url(), json=payload).status_code == 403


def test_batch_inference_queues_one_video_task_and_rejects_viewer(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "owner")
    viewer = client_for(app, "viewer")
    payload = {
        "model_id": "model-id",
        "categories": ["helmet", "dog"],
        "confidence": 0.25,
        "iou": 0.45,
        "overwrite": False,
    }
    batch_url = "/api/v1/projects/project-id/videos/video-id/auto-annotations"

    disabled = owner.put(
        "/api/v1/projects/project-id/videos/video-id/enabled",
        headers=ORIGIN,
        json={"enabled": False, "version": 1},
    )
    assert disabled.status_code == 200
    assert owner.post(batch_url, headers=ORIGIN, json=payload).status_code == 409
    assert owner.put(
        "/api/v1/projects/project-id/videos/video-id/enabled",
        headers=ORIGIN,
        json={"enabled": True, "version": 2},
    ).status_code == 200
    response = owner.post(batch_url, headers=ORIGIN, json=payload)

    assert response.status_code == 202
    assert response.json()["type"] == "auto_annotate"
    assert response.json()["video_id"] == "video-id"
    assert viewer.post(batch_url, headers=ORIGIN, json=payload).status_code == 403
    assert owner.post(batch_url, headers=ORIGIN, json=payload).status_code == 409


def test_project_batch_inference_queues_parent_task_and_reports_video_scope(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "owner")
    with Session(app.state.auth_service.engine) as session:
        session.add(
            Video(
                id="video-two",
                project_id="project-id",
                short_code="TESTV002",
                source_type="local",
                title="second",
                status="ready",
                width=1920,
                height=1080,
                enabled=True,
            )
        )
        session.flush()
        session.add(
            SamplingPlan(
                id="plan-two",
                video_id="video-two",
                mode="target_frames",
                parameters="{}",
                output_format="jpg",
                output_quality=2,
                expected_frames=1,
                extracted_frames=1,
                enabled_frames=1,
            )
        )
        session.add(
            Frame(
                id="frame-two",
                video_id="video-two",
                generation=1,
                sequence=1,
                source_frame_index=0,
                time_offset=0,
                file_path="projects/project-id/frames/TESTV002/frame.jpg",
                enabled=True,
            )
        )
        session.commit()

    response = owner.post(
        "/api/v1/projects/project-id/auto-annotations/batch",
        headers=ORIGIN,
        json={
            "video_ids": ["video-id", "video-two"],
            "model_id": "model-id",
            "categories": ["dog"],
            "confidence": 0.25,
            "iou": 0.45,
            "scope": "unannotated",
            "overwrite": False,
        },
    )
    assert response.status_code == 202, response.text
    body = response.json()
    assert body["accepted_video_ids"] == ["video-id", "video-two"]
    assert body["rejected"] == []
    assert body["task"]["video_id"] is None
    with Session(app.state.auth_service.engine) as session:
        task = session.get(Task, body["task"]["id"])
        assert task is not None
        assert json.loads(task.payload)["video_ids"] == ["video-id", "video-two"]

    conflict = owner.post(
        "/api/v1/projects/project-id/auto-annotations/batch",
        headers=ORIGIN,
        json={
            "video_ids": ["video-id"],
            "model_id": "model-id",
            "categories": [],
            "confidence": 0.25,
            "iou": 0.45,
            "scope": "all",
        },
    )
    assert conflict.status_code == 409
