from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import (
    DatasetExport,
    Frame,
    Project,
    ProjectLabel,
    ProjectMembership,
    SamplingPlan,
    Task,
    User,
    Video,
)
from vision_dataset_workbench.security.passwords import hash_password

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


def make_app(tmp_path, *, with_frame: bool = True):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    workspace.mkdir(parents=True)
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    password_hash = hash_password(PASSWORD)
    with Session(engine) as session:
        session.add_all(
            User(
                id=f"{name}-id",
                username=name,
                username_normalized=name,
                password_hash=password_hash,
                status="active",
            )
            for name in ("owner", "editor", "viewer", "outsider")
        )
        session.flush()
        session.add(Project(id="project-id", name="project", creator_id="owner-id"))
        session.add_all(
            [
                ProjectMembership(
                    project_id="project-id", user_id="editor-id", role="editor"
                ),
                ProjectMembership(
                    project_id="project-id", user_id="viewer-id", role="viewer"
                ),
            ]
        )
        session.add_all(
            [
                ProjectLabel(
                    id="person-label",
                    project_id="project-id",
                    name="person",
                    name_normalized="person",
                    color="#16866f",
                    sort_order=0,
                    enabled=True,
                ),
                ProjectLabel(
                    id="car-label",
                    project_id="project-id",
                    name="car",
                    name_normalized="car",
                    color="#e85d4a",
                    sort_order=1,
                    enabled=False,
                ),
            ]
        )
        session.add(
            Video(
                id="video-id",
                project_id="project-id",
                short_code="TESTV001",
                source_type="local",
                title="video",
                status="ready",
                enabled=True,
                width=1920,
                height=1080,
            )
        )
        session.flush()
        session.add(
            SamplingPlan(
                id="plan-id",
                video_id="video-id",
                mode="target_frames",
                parameters="{}",
                output_format="jpg",
                output_quality=2,
                expected_frames=1,
                extracted_frames=1 if with_frame else 0,
                enabled_frames=1 if with_frame else 0,
                generation=1 if with_frame else 0,
                applied_version=1 if with_frame else 0,
                frame_revision=1 if with_frame else 0,
            )
        )
        if with_frame:
            session.add(
                Frame(
                    id="frame-id",
                    video_id="video-id",
                    generation=1,
                    sequence=1,
                    source_frame_index=0,
                    time_offset=0,
                    file_path="projects/project-id/frames/TESTV001/TESTV001_frame_000001.jpg",
                    enabled=True,
                )
            )
        session.commit()
    engine.dispose()
    return create_app(RuntimeSettings(home=home, workspace=workspace))


def client_for(app, username):
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": username, "password": PASSWORD},
    )
    assert response.status_code == 200
    return client


def export_payload(*, all_disabled: bool = False):
    return {
        "name": "火灾/烟雾训练集",
        "train_ratio": 0.8,
        "labels": [
            {
                "source_label_id": "person-label",
                "name": "person",
                "mapping": 0,
                "enabled": not all_disabled,
            },
            {
                "source_label_id": "car-label",
                "name": "car",
                "mapping": 1,
                "enabled": False,
            },
        ],
    }


def test_export_create_validates_snapshot_permissions_and_active_limit(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "owner")
    editor = client_for(app, "editor")
    viewer = client_for(app, "viewer")

    invalid = export_payload()
    invalid["labels"][0]["name"] = "truck"
    assert owner.post(
        "/api/v1/projects/project-id/dataset-exports",
        headers=ORIGIN,
        json=invalid,
    ).status_code == 422
    assert owner.post(
        "/api/v1/projects/project-id/dataset-exports",
        headers=ORIGIN,
        json=export_payload(all_disabled=True),
    ).status_code == 422
    assert viewer.post(
        "/api/v1/projects/project-id/dataset-exports",
        headers=ORIGIN,
        json=export_payload(),
    ).status_code == 403

    created = editor.post(
        "/api/v1/projects/project-id/dataset-exports",
        headers=ORIGIN,
        json=export_payload(),
    )
    assert created.status_code == 202, created.text
    body = created.json()
    assert body["name"] == "火灾/烟雾训练集"
    assert body["status"] == "queued"
    assert body["labels"][1] == {
        "source_label_id": "car-label",
        "name": "car",
        "mapping": 1,
        "enabled": False,
    }

    assert owner.post(
        "/api/v1/projects/project-id/dataset-exports",
        headers=ORIGIN,
        json=export_payload(),
    ).status_code == 409
    listed = viewer.get("/api/v1/projects/project-id/dataset-exports").json()
    assert listed["total"] == 1
    export_id = listed["items"][0]["id"]
    detail = viewer.get(
        f"/api/v1/projects/project-id/dataset-exports/{export_id}"
    )
    assert detail.status_code == 200
    assert detail.json()["manifest"] is None
    assert client_for(app, "outsider").get(
        "/api/v1/projects/project-id/dataset-exports"
    ).status_code == 404

    with Session(app.state.auth_service.engine) as session:
        export_record = session.get(DatasetExport, export_id)
        task = session.get(Task, export_record.task_id)
        assert task is not None
        assert task.type == "export_dataset"


def test_export_requires_enabled_frames_and_same_origin(tmp_path):
    app = make_app(tmp_path, with_frame=False)
    owner = client_for(app, "owner")
    assert owner.post(
        "/api/v1/projects/project-id/dataset-exports", json=export_payload()
    ).status_code == 403
    assert owner.post(
        "/api/v1/projects/project-id/dataset-exports",
        headers=ORIGIN,
        json=export_payload(),
    ).status_code == 409
