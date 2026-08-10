from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import (
    Frame,
    FrameAnnotation,
    Project,
    ProjectLabel,
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
                    short_code="TESTV001",
                    source_type="local",
                    title="ready",
                    status="ready",
                    duration=300,
                    fps=30,
                    total_frames=9000,
                    file_path="projects/project-id/videos/TESTV001.mp4",
                ),
            ]
        )
        session.commit()
    (workspace / "projects/project-id/videos/TESTV001.mp4").write_bytes(b"video")
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


def configure(editor, overwrite_level="none"):
    return editor.post(
        "/api/v1/projects/project-id/sampling-plans",
        headers=ORIGIN,
        json={
            "video_ids": ["video-id"],
            "mode": "target_frames",
            "parameters": {"minimum": 50, "maximum": 200},
            "output_format": "jpg",
            "output_quality": 2,
            "overwrite_level": overwrite_level,
        },
    )


def test_editor_configures_and_queues_while_viewer_is_read_only(tmp_path):
    app = make_app(tmp_path)
    editor = client_for(app, "editor")
    viewer = client_for(app, "viewer")

    assert configure(editor).status_code == 200
    configured = configure(editor, "configured").json()
    assert configured["accepted"][0]["plan"]["expected_frames"] == 106
    listed = viewer.get("/api/v1/projects/project-id/videos").json()
    assert listed["items"][0]["sampling"]["state"] == "configured"
    assert listed["items"][0]["has_annotations"] is False
    assert listed["items"][0]["sampling"]["updated_at"].endswith("Z")
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
    frames_dir = app.state.workspace / "projects/project-id/frames/TESTV001"
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
            path = frames_dir / f"TESTV001_frame_{sequence:06d}.jpg"
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
        session.add(
            ProjectLabel(
                id="label-id",
                project_id="project-id",
                name="helmet",
                name_normalized="helmet",
                color="#16866f",
                sort_order=0,
            )
        )
        session.flush()
        session.add(
            FrameAnnotation(
                id="annotation-id",
                frame_id="frame-1",
                label_id="label-id",
                x_min=10,
                y_min=20,
                x_max=110,
                y_max=220,
                source="manual",
                sort_order=0,
            )
        )
        session.commit()

    page = viewer.get(
        "/api/v1/projects/project-id/videos/video-id/frames?page=1&page_size=1"
    )
    assert page.status_code == 200
    assert page.json()["total"] == 2
    assert page.json()["items"][0]["file_size"] == len(b"frame-1")
    assert "annotations" not in page.json()["items"][0]
    preview = viewer.get(
        "/api/v1/projects/project-id/videos/video-id/frames"
        "?page=1&page_size=2&include_annotations=true"
    )
    assert preview.status_code == 200
    assert preview.json()["items"][0]["annotations"] == [
        {
            "id": "annotation-id",
            "label_id": "label-id",
            "x_min": 10,
            "y_min": 20,
            "x_max": 110,
            "y_max": 220,
        }
    ]
    assert preview.json()["items"][1]["annotations"] == []
    assert viewer.get(
        "/api/v1/projects/project-id/videos/video-id/frames/frame-1/image"
    ).content == b"frame-1"
    assert outsider.get(
        "/api/v1/projects/project-id/videos/video-id/frames"
    ).status_code == 404
    summary = viewer.get(
        "/api/v1/projects/project-id/videos/video-id/frames/annotation-summary"
    )
    assert summary.status_code == 200
    assert summary.json() == {"annotated_frame_ids": ["frame-1"]}
    payload = {
        "changes": [
            {"frame_id": "frame-1", "enabled": False},
            {"frame_id": "frame-2", "enabled": True},
        ],
        "frame_revision": 1,
    }
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
    with Session(app.state.auth_service.engine) as session:
        assert session.get(Frame, "frame-1").enabled is False
        assert session.get(Frame, "frame-2").enabled is True
    assert editor.put(
        "/api/v1/projects/project-id/videos/video-id/frames/enabled",
        headers=ORIGIN,
        json=payload,
    ).status_code == 409
    duplicate = {
        "changes": [
            {"frame_id": "frame-1", "enabled": True},
            {"frame_id": "frame-1", "enabled": False},
        ],
        "frame_revision": 2,
    }
    assert editor.put(
        "/api/v1/projects/project-id/videos/video-id/frames/enabled",
        headers=ORIGIN,
        json=duplicate,
    ).status_code == 422


def test_batch_enabled_by_annotation_supports_scope_and_mixed_results(tmp_path):
    app = make_app(tmp_path)
    editor = client_for(app, "editor")
    frames_dir = app.state.workspace / "projects/project-id/frames/TESTV001"
    frames_dir.mkdir(parents=True)
    with Session(app.state.auth_service.engine) as session:
        session.add(
            Video(
                id="video-two",
                project_id="project-id",
                short_code="TESTV002",
                source_type="local",
                title="second",
                status="ready",
                duration=120,
                fps=30,
                total_frames=3600,
            )
        )
        session.add(
            ProjectLabel(
                id="label-id",
                project_id="project-id",
                name="person",
                name_normalized="person",
                color="#16866f",
                sort_order=0,
            )
        )
        session.flush()
        for video_id, frame_id, short_code, enabled in (
            ("video-id", "annotated-frame", "TESTV001", True),
            ("video-two", "empty-frame", "TESTV002", True),
        ):
            session.add(
                SamplingPlan(
                    id=f"plan-{video_id}",
                    video_id=video_id,
                    mode="target_frames",
                    parameters="{}",
                    output_format="jpg",
                    output_quality=2,
                    expected_frames=1,
                    extracted_frames=1,
                    enabled_frames=1,
                    applied_version=1,
                    generation=1,
                    frame_revision=1,
                )
            )
            session.add(
                Frame(
                    id=frame_id,
                    video_id=video_id,
                    generation=1,
                    sequence=1,
                    source_frame_index=0,
                    time_offset=0,
                    file_path=f"projects/project-id/frames/{short_code}/{short_code}_frame_000001.jpg",
                    enabled=enabled,
                )
            )
        session.flush()
        session.add(
            FrameAnnotation(
                id="annotation-id",
                frame_id="annotated-frame",
                label_id="label-id",
                x_min=1,
                y_min=1,
                x_max=20,
                y_max=20,
                source="manual",
            )
        )
        session.commit()

    unscreened_only = editor.post(
        "/api/v1/projects/project-id/videos/batch-enabled-by-annotation",
        headers=ORIGIN,
        json={
            "video_ids": ["video-id", "video-two"],
            "scope": "unscreened-only",
            "revisions": {"video-id": 1, "video-two": 1},
        },
    )
    assert unscreened_only.status_code == 200
    assert [item["video_id"] for item in unscreened_only.json()["accepted"]] == ["video-id"]
    assert unscreened_only.json()["rejected"][0]["code"] == "no_annotations"

    repeated_unscreened = editor.post(
        "/api/v1/projects/project-id/videos/batch-enabled-by-annotation",
        headers=ORIGIN,
        json={
            "video_ids": ["video-id", "video-two"],
            "scope": "unscreened-only",
        },
    )
    assert repeated_unscreened.status_code == 200
    assert repeated_unscreened.json()["accepted"] == []
    assert {item["code"] for item in repeated_unscreened.json()["rejected"]} == {
        "already_screened",
        "no_annotations",
    }

    rejected_confirmation = editor.post(
        "/api/v1/projects/project-id/videos/batch-enabled-by-annotation",
        headers=ORIGIN,
        json={"video_ids": ["video-id", "video-two"], "scope": "all"},
    )
    assert rejected_confirmation.status_code == 409

    all_videos = editor.post(
        "/api/v1/projects/project-id/videos/batch-enabled-by-annotation",
        headers=ORIGIN,
        json={
            "video_ids": ["video-id", "video-two"],
            "scope": "all",
            "confirm_all": True,
        },
    )
    assert all_videos.status_code == 200
    assert [item["video_id"] for item in all_videos.json()["accepted"]] == ["video-id"]
    assert all_videos.json()["rejected"][0]["code"] == "no_annotations"
    with Session(app.state.auth_service.engine) as session:
        assert session.get(Frame, "annotated-frame").enabled is True
        assert session.get(Frame, "empty-frame").enabled is True
