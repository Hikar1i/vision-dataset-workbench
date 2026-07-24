from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import (
    Frame,
    Project,
    ProjectMembership,
    SamplingPlan,
    User,
    Video,
)
from vision_dataset_workbench.security.passwords import hash_password

PASSWORD = "correct horse battery staple"
ORIGIN = {"Origin": "http://testserver"}


def make_app(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects/project-id/videos").mkdir(parents=True)
    database_path = workspace / "db/workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    password_hash = hash_password(PASSWORD)
    with Session(engine) as session:
        for name in ("owner", "editor", "viewer", "outsider"):
            session.add(
                User(
                    id=f"{name}-id",
                    username=name,
                    username_normalized=name,
                    password_hash=password_hash,
                    status="active",
                )
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
                Video(
                    id="video-id",
                    project_id="project-id",
                    source_type="local",
                    title="ready",
                    status="ready",
                    duration=300,
                    fps=30,
                    total_frames=9000,
                    file_path="projects/project-id/videos/video-id.mp4",
                ),
            ]
        )
        session.commit()
    (workspace / "projects/project-id/videos/video-id.mp4").write_bytes(b"video")
    engine.dispose()
    return create_app(RuntimeSettings(home=home, workspace=workspace))


def client_for(app, username):
    client = TestClient(app)
    assert client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": username, "password": PASSWORD},
    ).status_code == 200
    return client


def configure(editor):
    return editor.post(
        "/api/v1/projects/project-id/sampling-plans",
        headers=ORIGIN,
        json={
            "video_ids": ["video-id"],
            "mode": "target_frames",
            "parameters": {"minimum": 50, "maximum": 200},
            "output_format": "jpg",
            "output_quality": 2,
        },
    )


def test_editor_configures_and_queues_while_viewer_is_read_only(tmp_path):
    app = make_app(tmp_path)
    editor = client_for(app, "editor")
    viewer = client_for(app, "viewer")

    assert configure(editor).status_code == 200
    configured = configure(editor).json()
    assert configured["accepted"][0]["plan"]["expected_frames"] == 106
    listed = viewer.get("/api/v1/projects/project-id/videos").json()
    assert listed["items"][0]["sampling"]["state"] == "configured"
    assert viewer.get(
        "/api/v1/projects/project-id/videos/video-id/sampling-plan"
    ).status_code == 200
    assert configure(viewer).status_code == 403
    assert editor.post(
        "/api/v1/projects/project-id/extractions",
        json={"video_ids": ["video-id"]},
    ).status_code == 403

    queued = editor.post(
        "/api/v1/projects/project-id/extractions",
        headers=ORIGIN,
        json={"video_ids": ["video-id"]},
    )
    assert queued.status_code == 202
    assert queued.json()["accepted"][0]["task"]["type"] == "extract_frames"
    assert viewer.post(
        "/api/v1/projects/project-id/extractions",
        headers=ORIGIN,
        json={"video_ids": ["video-id"]},
    ).status_code == 403


def test_viewer_reads_frame_image_and_editor_filters_with_revision(tmp_path):
    app = make_app(tmp_path)
    editor = client_for(app, "editor")
    viewer = client_for(app, "viewer")
    outsider = client_for(app, "outsider")
    assert configure(editor).status_code == 200
    frames_dir = app.state.workspace / "projects/project-id/frames/video-id"
    frames_dir.mkdir(parents=True)
    with Session(app.state.auth_service.engine) as session:
        plan = session.scalar(select(SamplingPlan))
        assert plan is not None
        plan.applied_version = plan.version
        plan.generation = 1
        plan.extracted_frames = 2
        plan.enabled_frames = 2
        plan.frame_revision = 1
        for sequence in (1, 2):
            path = frames_dir / f"{sequence:06d}.jpg"
            path.write_bytes(f"frame-{sequence}".encode())
            session.add(
                Frame(
                    id=f"frame-{sequence}",
                    video_id="video-id",
                    generation=1,
                    sequence=sequence,
                    source_frame_index=sequence - 1,
                    time_offset=(sequence - 1) / 30,
                    file_path=path.relative_to(app.state.workspace).as_posix(),
                )
            )
        session.commit()

    page = viewer.get(
        "/api/v1/projects/project-id/videos/video-id/frames?page=1&page_size=1"
    )
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert viewer.get(
        "/api/v1/projects/project-id/videos/video-id/frames/frame-1/image"
    ).content == b"frame-1"
    assert outsider.get(
        "/api/v1/projects/project-id/videos/video-id/frames"
    ).status_code == 404
    payload = {"enabled": False, "frame_ids": ["frame-1"], "frame_revision": 1}
    assert viewer.put(
        "/api/v1/projects/project-id/videos/video-id/frames/enabled",
        headers=ORIGIN,
        json=payload,
    ).status_code == 403
    changed = editor.put(
        "/api/v1/projects/project-id/videos/video-id/frames/enabled",
        headers=ORIGIN,
        json=payload,
    )
    assert changed.status_code == 200
    assert changed.json()["enabled_frames"] == 1
    assert editor.put(
        "/api/v1/projects/project-id/videos/video-id/frames/enabled",
        headers=ORIGIN,
        json=payload,
    ).status_code == 409
