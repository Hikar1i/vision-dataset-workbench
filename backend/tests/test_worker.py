import hashlib
import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.media import MediaMetadata
from vision_dataset_workbench.models import Project, Task, User, Video
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.worker import TaskWorker, download_command


def make_worker(tmp_path, *, probe=None):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects" / "project-id").mkdir(parents=True)
    (home / "clips").mkdir()
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    with Session(engine) as session:
        for name in ("one", "two"):
            session.add(
                User(
                    id=f"{name}-id",
                    username=name,
                    username_normalized=name,
                    password_hash=hash_password("correct horse battery staple"),
                )
            )
        session.flush()
        session.add(Project(id="project-id", name="project", creator_id="one-id"))
        session.commit()
    settings = RuntimeSettings(home=home, workspace=workspace)
    worker = TaskWorker(
        engine,
        settings,
        workspace,
        probe=probe
        or (lambda path: MediaMetadata(1, 320, 240, 25, 25, path.stat().st_size)),
    )
    return worker, engine, home, workspace


def add_task(engine, *, task_id, user_id, task_type="copy_video", payload=None):
    with Session(engine) as session:
        video = Video(
            id=f"video-{task_id}",
            project_id="project-id",
            source_type="local" if task_type == "copy_video" else "remote",
            title=task_id,
        )
        session.add(video)
        session.flush()
        session.add(
            Task(
                id=task_id,
                project_id="project-id",
                submitted_by_id=user_id,
                video_id=video.id,
                type=task_type,
                payload=json.dumps(payload or {}),
            )
        )
        session.commit()


def test_claim_respects_type_and_user_limits_and_recovers_expired_lease(tmp_path):
    worker, engine, _home, _workspace = make_worker(tmp_path)
    add_task(engine, task_id="copy-one-a", user_id="one-id")
    add_task(engine, task_id="copy-one-b", user_id="one-id")
    add_task(engine, task_id="copy-two", user_id="two-id")
    add_task(
        engine,
        task_id="download-one",
        user_id="one-id",
        task_type="download_video",
    )
    with Session(engine) as session:
        expired = session.get(Task, "copy-two")
        assert expired is not None
        expired.status = "running"
        expired.lease_owner = "dead-worker"
        expired.lease_expires_at = (
            datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(seconds=1)
        )
        session.commit()

    claimed = worker.claim_available()

    assert {task.id for task in claimed} == {
        "copy-one-a",
        "copy-two",
        "download-one",
    }
    assert all(task.status == "running" for task in claimed)
    engine.dispose()


def test_copy_task_publishes_metadata_and_hash(tmp_path):
    worker, engine, home, workspace = make_worker(tmp_path)
    source = home / "clips" / "one.MKV"
    source.write_bytes(b"video bytes")
    add_task(
        engine,
        task_id="copy-task",
        user_id="one-id",
        payload={"source_path": "clips/one.MKV"},
    )
    assert worker.claim_available()[0].id == "copy-task"

    worker.execute_task("copy-task")

    with Session(engine) as session:
        task = session.get(Task, "copy-task")
        video = session.get(Video, "video-copy-task")
        assert task is not None and task.status == "succeeded"
        assert task.progress == 100
        assert video is not None and video.status == "ready"
        assert video.content_sha256 == hashlib.sha256(b"video bytes").hexdigest()
        assert video.file_path == "projects/project-id/videos/video-copy-task.mkv"
        assert (workspace / video.file_path).read_bytes() == b"video bytes"
        assert video.width == 320
    engine.dispose()


def test_copy_cancel_and_duplicate_are_safe(tmp_path):
    worker, engine, home, workspace = make_worker(tmp_path)
    source = home / "clips" / "same.mp4"
    source.write_bytes(b"same")
    digest = hashlib.sha256(b"same").hexdigest()
    with Session(engine) as session:
        session.add(
            Video(
                id="existing",
                project_id="project-id",
                source_type="local",
                title="existing",
                content_sha256=digest,
                file_path="projects/project-id/videos/existing.mp4",
                status="ready",
            )
        )
        session.commit()

    add_task(
        engine,
        task_id="duplicate-task",
        user_id="one-id",
        payload={"source_path": "clips/same.mp4"},
    )
    add_task(
        engine,
        task_id="cancel-task",
        user_id="two-id",
        payload={"source_path": "clips/same.mp4"},
    )
    claimed = worker.claim_available()
    assert len(claimed) == 2
    with Session(engine) as session:
        cancel = session.get(Task, "cancel-task")
        assert cancel is not None
        cancel.cancel_requested = True
        session.commit()

    worker.execute_task("duplicate-task")
    worker.execute_task("cancel-task")

    with Session(engine) as session:
        duplicate = session.get(Task, "duplicate-task")
        canceled = session.get(Task, "cancel-task")
        assert duplicate is not None and duplicate.status == "succeeded"
        assert json.loads(duplicate.result or "{}")["outcome"] == "skipped"
        assert duplicate.video_id is None
        assert canceled is not None and canceled.status == "canceled"
        assert session.get(Video, "video-duplicate-task") is None
        assert not (workspace / "projects/project-id/videos/video-duplicate-task.mp4").exists()
    engine.dispose()


def test_download_command_keeps_legacy_quality_without_insecure_tls(tmp_path):
    settings = RuntimeSettings(home=tmp_path, workspace=None)
    command = download_command(
        settings,
        "https://example.test/video",
        tmp_path / "video-id.%(ext)s",
    )

    assert any("bestvideo[height<=1080]+bestaudio" in argument for argument in command)
    assert "--merge-output-format" in command
    assert "--write-thumbnail" in command
    assert "--no-check-certificates" not in command
