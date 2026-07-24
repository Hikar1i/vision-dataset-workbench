import hashlib
import io
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.media import MediaMetadata
from vision_dataset_workbench.models import Frame, Project, SamplingPlan, Task, User, Video
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.worker import TaskWorker, download_command


def make_worker(tmp_path, *, probe=None, popen=None):
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
        **({"popen": popen} if popen else {}),
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


class FakeExtractionProcess:
    def __init__(self, command, frame_count=3):
        self.command = command
        self.returncode = 0
        self._polls = 0
        output_pattern = command[-1]
        for sequence in range(1, frame_count + 1):
            path = output_pattern.replace("%06d", f"{sequence:06d}")
            Path(path).write_bytes(f"frame-{sequence}".encode())
        self.stdout = io.StringIO(
            f"frame=1\nprogress=continue\nframe={frame_count}\nprogress=end\n"
        )

    def poll(self):
        self._polls += 1
        return None if self._polls < 3 else self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def wait(self, timeout=None):
        return self.returncode


def add_extraction(engine, workspace, *, plan_version=1, output_format="jpg"):
    video_path = workspace / "projects/project-id/videos/video-id.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")
    with Session(engine) as session:
        session.add(
            Video(
                id="video-id",
                project_id="project-id",
                source_type="local",
                title="video",
                status="ready",
                file_path="projects/project-id/videos/video-id.mp4",
                duration=10,
                fps=10,
                total_frames=100,
            )
        )
        session.flush()
        session.add(
            SamplingPlan(
                id="plan-id",
                video_id="video-id",
                mode="target_frames",
                parameters='{"minimum": 10, "maximum": 100}',
                output_format=output_format,
                output_quality=2 if output_format == "jpg" else 6,
                expected_frames=3,
                version=plan_version,
            )
        )
        session.add(
            Task(
                id="extract-task",
                project_id="project-id",
                submitted_by_id="one-id",
                video_id="video-id",
                type="extract_frames",
                payload=json.dumps({"sampling_plan_version": plan_version}),
            )
        )
        session.commit()


def test_extract_task_publishes_stable_frames_and_plan_counts(tmp_path):
    commands = []

    def popen(command, **_kwargs):
        commands.append(command)
        return FakeExtractionProcess(command)

    worker, engine, _home, workspace = make_worker(tmp_path, popen=popen)
    add_extraction(engine, workspace)
    assert worker.claim_available()[0].id == "extract-task"

    worker.execute_task("extract-task")

    with Session(engine) as session:
        task = session.get(Task, "extract-task")
        plan = session.get(SamplingPlan, "plan-id")
        frames = session.query(Frame).order_by(Frame.sequence).all()
        assert task is not None and task.status == "succeeded"
        assert plan is not None and plan.applied_version == 1
        assert plan.extracted_frames == plan.enabled_frames == 3
        assert plan.generation == plan.frame_revision == 1
        assert [frame.source_frame_index for frame in frames] == [0, 34, 67]
        assert all((workspace / frame.file_path).is_file() for frame in frames)
    assert "-progress" in commands[0]
    assert "-threads" in commands[0]
    assert any("floor" in value for value in commands[0])
    engine.dispose()


def test_extract_rejects_changed_plan_and_preserves_existing_frames(tmp_path):
    worker, engine, _home, workspace = make_worker(
        tmp_path, popen=lambda command, **_kwargs: FakeExtractionProcess(command)
    )
    add_extraction(engine, workspace, plan_version=2)
    old_dir = workspace / "projects/project-id/frames/video-id"
    old_dir.mkdir(parents=True)
    old_path = old_dir / "000001.jpg"
    old_path.write_bytes(b"old")
    with Session(engine) as session:
        plan = session.get(SamplingPlan, "plan-id")
        assert plan is not None
        plan.version = 3
        plan.applied_version = 2
        plan.generation = 1
        plan.extracted_frames = 1
        plan.enabled_frames = 1
        plan.frame_revision = 1
        session.add(
            Frame(
                id="old-frame",
                video_id="video-id",
                generation=1,
                sequence=1,
                source_frame_index=0,
                time_offset=0,
                file_path=old_path.relative_to(workspace).as_posix(),
            )
        )
        session.commit()
    worker.claim_available()

    worker.execute_task("extract-task")

    with Session(engine) as session:
        task = session.get(Task, "extract-task")
        assert task is not None and task.status == "failed"
        assert "sampling plan changed" in (task.error or "")
        assert session.query(Frame).one().id == "old-frame"
    assert old_path.read_bytes() == b"old"
    engine.dispose()


def test_resampling_replaces_previous_generation(tmp_path):
    frame_counts = iter((3, 2))
    worker, engine, _home, workspace = make_worker(
        tmp_path,
        popen=lambda command, **_kwargs: FakeExtractionProcess(
            command, next(frame_counts)
        ),
    )
    add_extraction(engine, workspace)
    worker.claim_available()
    worker.execute_task("extract-task")
    with Session(engine) as session:
        old_ids = set(session.scalars(select(Frame.id)))
        plan = session.get(SamplingPlan, "plan-id")
        assert plan is not None
        plan.version = 2
        plan.expected_frames = 2
        session.add(
            Task(
                id="resample-task",
                project_id="project-id",
                submitted_by_id="one-id",
                video_id="video-id",
                type="extract_frames",
                payload=json.dumps({"sampling_plan_version": 2}),
            )
        )
        session.commit()

    worker.claim_available()
    worker.execute_task("resample-task")

    with Session(engine) as session:
        frames = session.query(Frame).order_by(Frame.sequence).all()
        plan = session.get(SamplingPlan, "plan-id")
        assert len(frames) == 2
        assert not old_ids.intersection(frame.id for frame in frames)
        assert plan is not None and plan.generation == 2
        assert plan.applied_version == 2
    target = workspace / "projects/project-id/frames/video-id"
    assert [path.name for path in sorted(target.iterdir())] == [
        "000001.jpg",
        "000002.jpg",
    ]
    engine.dispose()
