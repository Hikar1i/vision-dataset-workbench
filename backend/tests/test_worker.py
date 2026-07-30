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
from vision_dataset_workbench.models import (
    DatasetExport,
    Frame,
    FrameAnnotation,
    InferenceModel,
    Project,
    ProjectLabel,
    SamplingPlan,
    Task,
    User,
    Video,
)
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.worker import TaskWorker, download_command


def make_worker(tmp_path, *, probe=None, popen=None, inference_runner=None):
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
        **({"inference_runner": inference_runner} if inference_runner else {}),
    )
    return worker, engine, home, workspace


def add_task(
    engine,
    *,
    task_id,
    user_id,
    task_type="copy_video",
    payload=None,
    short_code=None,
):
    with Session(engine) as session:
        video = Video(
            id=f"video-{task_id}",
            project_id="project-id",
            short_code=short_code
            or hashlib.sha256(task_id.encode()).hexdigest()[:8].upper(),
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
        short_code="TESTV001",
    )
    assert worker.claim_available()[0].id == "copy-task"

    worker.execute_task("copy-task")

    with Session(engine) as session:
        task = session.get(Task, "copy-task")
        video = session.get(Video, "video-copy-task")
        assert task is not None and task.status == "succeeded", task.error if task else None
        assert task.progress == 100
        assert video is not None and video.status == "ready"
        assert video.content_sha256 == hashlib.sha256(b"video bytes").hexdigest()
        assert video.file_path == "projects/project-id/videos/TESTV001.mkv"
        assert (workspace / video.file_path).read_bytes() == b"video bytes"
        assert video.width == 320
    engine.dispose()


def test_import_model_task_copies_into_managed_storage(tmp_path):
    worker, engine, home, workspace = make_worker(tmp_path)
    source = home / "models" / "detector.pt"
    source.parent.mkdir()
    source.write_bytes(b"weights")
    with Session(engine) as session:
        session.add(
            InferenceModel(
                id="model-id",
                name="detector",
                kind="yolo",
                status="copying",
                source_name="detector.pt",
                created_by_id="one-id",
            )
        )
        session.add(
            Task(
                id="import-model",
                project_id="project-id",
                submitted_by_id="one-id",
                type="import_model",
                payload=json.dumps({"model_id": "model-id", "source_path": "models/detector.pt"}),
            )
        )
        session.commit()

    assert worker.claim_available()[0].id == "import-model"
    worker.execute_task("import-model")

    with Session(engine) as session:
        task = session.get(Task, "import-model")
        model = session.get(InferenceModel, "model-id")
        assert task is not None and task.status == "succeeded"
        assert model is not None and model.status == "ready"
        assert model.storage_path == "models/model-id/detector.pt"
        assert (workspace / model.storage_path).read_bytes() == b"weights"
    engine.dispose()


def test_auto_annotation_task_processes_only_starting_enabled_frames(tmp_path):
    from vision_dataset_workbench.inference import Detection

    class Runner:
        def predict(self, *_args, **_kwargs):
            return [Detection("dog", 10, 20, 110, 220, 0.9)]

    worker, engine, _home, workspace = make_worker(
        tmp_path, inference_runner=Runner()
    )
    model_path = workspace / "models" / "model-id" / "model.pt"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"weights")
    frames_dir = workspace / "projects" / "project-id" / "frames" / "TESTV001"
    frames_dir.mkdir(parents=True)
    with Session(engine) as session:
        session.add(
            Video(
                id="video-id",
                project_id="project-id",
                short_code="TESTV001",
                source_type="local",
                title="video",
                status="ready",
                width=320,
                height=240,
                enabled=True,
            )
        )
        session.add(
            InferenceModel(
                id="model-id",
                name="detector",
                kind="yolo",
                status="ready",
                storage_path="models/model-id/model.pt",
                source_name="model.pt",
                created_by_id="one-id",
            )
        )
        session.add(
            ProjectLabel(
                id="helmet-label",
                project_id="project-id",
                name="helmet",
                name_normalized="helmet",
                color="#16866f",
                sort_order=0,
                enabled=True,
            )
        )
        session.flush()
        for sequence, enabled in ((1, True), (2, False)):
            path = frames_dir / f"TESTV001_frame_{sequence:06d}.jpg"
            path.write_bytes(b"image")
            session.add(
                Frame(
                    id=f"frame-{sequence}",
                    video_id="video-id",
                    generation=1,
                    sequence=sequence,
                    source_frame_index=sequence - 1,
                    time_offset=0,
                    file_path=path.relative_to(workspace).as_posix(),
                    enabled=enabled,
                )
            )
        session.flush()
        session.add(
            FrameAnnotation(
                id="manual-box",
                frame_id="frame-1",
                label_id="helmet-label",
                x_min=1,
                y_min=2,
                x_max=30,
                y_max=40,
                source="manual",
            )
        )
        session.add(
            Task(
                id="auto-task",
                project_id="project-id",
                submitted_by_id="one-id",
                video_id="video-id",
                type="auto_annotate",
                payload=json.dumps(
                    {
                        "model_id": "model-id",
                        "categories": ["dog"],
                        "confidence": 0.25,
                        "iou": 0.45,
                        "overwrite": False,
                    }
                ),
            )
        )
        session.commit()

    assert worker.claim_available()[0].id == "auto-task"
    worker.execute_task("auto-task")

    with Session(engine) as session:
        task = session.get(Task, "auto-task")
        first = session.get(Frame, "frame-1")
        second = session.get(Frame, "frame-2")
        first_boxes = (
            session.query(FrameAnnotation)
            .filter_by(frame_id="frame-1")
            .order_by(FrameAnnotation.sort_order)
            .all()
        )
        second_boxes = session.query(FrameAnnotation).filter_by(frame_id="frame-2").all()
        assert task is not None and task.status == "succeeded", task.error if task else None
        assert json.loads(task.result or "{}")["frames"] == 1
        assert {item.source for item in first_boxes} == {"manual", "model"}
        assert [(item.source, item.sort_order) for item in first_boxes] == [
            ("manual", 0),
            ("model", 1),
        ]
        assert second_boxes == []
        assert first is not None and first.enabled is True and first.annotation_revision == 2
        assert second is not None and second.enabled is False and second.annotation_revision == 1

        session.add(
            Task(
                id="auto-overwrite",
                project_id="project-id",
                submitted_by_id="one-id",
                video_id="video-id",
                type="auto_annotate",
                payload=json.dumps(
                    {
                        "model_id": "model-id",
                        "categories": ["dog"],
                        "confidence": 0.25,
                        "iou": 0.45,
                        "overwrite": True,
                    }
                ),
            )
        )
        session.commit()

    assert worker.claim_available()[0].id == "auto-overwrite"
    worker.execute_task("auto-overwrite")

    with Session(engine) as session:
        overwritten = session.query(FrameAnnotation).filter_by(frame_id="frame-1").all()
        assert [item.source for item in overwritten] == ["model"]
        assert overwritten[0].sort_order == 0
    engine.dispose()


def add_dataset_export_task(engine, workspace, *, missing_source=False):
    frames_dir = workspace / "projects" / "project-id" / "frames" / "TESTV001"
    frames_dir.mkdir(parents=True)
    with Session(engine) as session:
        session.add(
            Video(
                id="export-video",
                project_id="project-id",
                short_code="TESTV001",
                source_type="local",
                title="export video",
                status="ready",
                enabled=True,
                width=320,
                height=240,
                version=1,
            )
        )
        session.flush()
        session.add(
            SamplingPlan(
                id="export-plan",
                video_id="export-video",
                mode="target_frames",
                parameters="{}",
                output_format="jpg",
                output_quality=2,
                expected_frames=3,
                extracted_frames=3,
                enabled_frames=2,
                version=1,
                applied_version=1,
                generation=1,
                frame_revision=1,
            )
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
                    enabled=True,
                ),
            ]
        )
        for sequence, enabled in ((1, True), (2, True), (3, False)):
            path = frames_dir / f"TESTV001_frame_{sequence:06d}.jpg"
            if not (missing_source and sequence == 2):
                path.write_bytes(f"frame-{sequence}".encode())
            session.add(
                Frame(
                    id=f"export-frame-{sequence}",
                    video_id="export-video",
                    generation=1,
                    sequence=sequence,
                    source_frame_index=sequence - 1,
                    time_offset=sequence / 10,
                    file_path=path.relative_to(workspace).as_posix(),
                    enabled=enabled,
                )
            )
        session.flush()
        session.add_all(
            [
                FrameAnnotation(
                    id="person-box-1",
                    frame_id="export-frame-1",
                    label_id="person-label",
                    x_min=1,
                    y_min=2,
                    x_max=30,
                    y_max=40,
                    source="manual",
                    sort_order=0,
                ),
                FrameAnnotation(
                    id="car-box-1",
                    frame_id="export-frame-1",
                    label_id="car-label",
                    x_min=32,
                    y_min=24,
                    x_max=160,
                    y_max=120,
                    source="model",
                    confidence=0.9,
                    sort_order=1,
                ),
                FrameAnnotation(
                    id="person-box-2",
                    frame_id="export-frame-2",
                    label_id="person-label",
                    x_min=10,
                    y_min=20,
                    x_max=100,
                    y_max=200,
                    source="manual",
                ),
            ]
        )
        task = Task(
            id="dataset-export-task",
            project_id="project-id",
            submitted_by_id="one-id",
            type="export_dataset",
            payload=json.dumps({"export_id": "dataset-export"}),
        )
        session.add(task)
        session.flush()
        session.add(
            DatasetExport(
                id="dataset-export",
                project_id="project-id",
                task_id=task.id,
                created_by_id="one-id",
                name="训练集",
                status="queued",
                train_ratio=1,
                label_snapshot=json.dumps(
                    [
                        {
                            "source_label_id": "person-label",
                            "name": "person",
                            "mapping": 0,
                            "enabled": False,
                        },
                        {
                            "source_label_id": "car-label",
                            "name": "car",
                            "mapping": 1,
                            "enabled": True,
                        },
                    ]
                ),
                source_snapshot=json.dumps(
                    {
                        "videos": [
                            {
                                "video_id": "export-video",
                                "video_version": 1,
                                "sampling_generation": 1,
                                "frame_revision": 1,
                                "enabled_frames": 2,
                            }
                        ]
                    }
                ),
            )
        )
        session.commit()


def test_dataset_export_task_hardlinks_images_and_writes_sparse_labels(tmp_path):
    worker, engine, _home, workspace = make_worker(tmp_path)
    add_dataset_export_task(engine, workspace)
    assert worker.claim_available()[0].id == "dataset-export-task"

    worker.execute_task("dataset-export-task")

    with Session(engine) as session:
        task = session.get(Task, "dataset-export-task")
        record = session.get(DatasetExport, "dataset-export")
        assert task is not None and task.status == "succeeded", task.error if task else None
        assert record is not None and record.status == "ready"
        assert (record.total_frames, record.train_frames, record.val_frames) == (2, 2, 0)
        assert record.actual_train_ratio == 1
        target = workspace / str(record.storage_path)
        manifest = json.loads(record.manifest or "{}")

    first_source = workspace / "projects/project-id/frames/TESTV001/TESTV001_frame_000001.jpg"
    first_export = target / "train/images/TESTV001_frame_000001.jpg"
    assert first_export.stat().st_ino == first_source.stat().st_ino
    assert (target / "train/labels/TESTV001_frame_000001.txt").read_text() == (
        "1 0.300000 0.300000 0.400000 0.400000\n"
    )
    assert (target / "train/labels/TESTV001_frame_000002.txt").read_text() == ""
    assert not (target / "train/images/TESTV001_frame_000003.jpg").exists()
    assert (target / "classes.txt").read_text() == "person\ncar\n"
    assert "nc: 2" in (target / "dataset.yaml").read_text()
    assert manifest["train_video_ids"] == ["export-video"]
    assert manifest["video_stats"][0]["positive_frames"] == 1
    assert manifest["video_stats"][0]["negative_frames"] == 1
    engine.dispose()


def test_dataset_export_failure_does_not_publish_partial_directory(tmp_path):
    worker, engine, _home, workspace = make_worker(tmp_path)
    add_dataset_export_task(engine, workspace, missing_source=True)
    worker.claim_available()

    worker.execute_task("dataset-export-task")

    with Session(engine) as session:
        task = session.get(Task, "dataset-export-task")
        record = session.get(DatasetExport, "dataset-export")
        assert task is not None and task.status == "failed"
        assert record is not None and record.status == "failed"
        assert record.storage_path is None
    exports = workspace / "projects/project-id/exports"
    assert not exports.exists() or list(exports.iterdir()) == []
    engine.dispose()


def test_dataset_export_cancellation_updates_export_record(tmp_path):
    worker, engine, _home, workspace = make_worker(tmp_path)
    add_dataset_export_task(engine, workspace)
    worker.claim_available()
    with Session(engine) as session:
        task = session.get(Task, "dataset-export-task")
        task.cancel_requested = True
        session.commit()

    worker.execute_task("dataset-export-task")

    with Session(engine) as session:
        task = session.get(Task, "dataset-export-task")
        record = session.get(DatasetExport, "dataset-export")
        assert task is not None and task.status == "canceled"
        assert record is not None and record.status == "canceled"
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
    video_path = workspace / "projects/project-id/videos/TESTV001.mp4"
    video_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"video")
    with Session(engine) as session:
        session.add(
            Video(
                id="video-id",
                project_id="project-id",
                short_code="TESTV001",
                source_type="local",
                title="video",
                status="ready",
                file_path="projects/project-id/videos/TESTV001.mp4",
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
        assert [Path(frame.file_path).name for frame in frames] == [
            "TESTV001_frame_000001.jpg",
            "TESTV001_frame_000002.jpg",
            "TESTV001_frame_000003.jpg",
        ]
        assert all((workspace / frame.file_path).is_file() for frame in frames)
    assert "-progress" in commands[0]
    assert "-threads" in commands[0]
    assert commands[0][commands[0].index("-vsync") + 1] == "vfr"
    assert any("floor" in value for value in commands[0])
    engine.dispose()


def test_extract_rejects_changed_plan_and_preserves_existing_frames(tmp_path):
    worker, engine, _home, workspace = make_worker(
        tmp_path, popen=lambda command, **_kwargs: FakeExtractionProcess(command)
    )
    add_extraction(engine, workspace, plan_version=2)
    old_dir = workspace / "projects/project-id/frames/TESTV001"
    old_dir.mkdir(parents=True)
    old_path = old_dir / "TESTV001_frame_000001.jpg"
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
    target = workspace / "projects/project-id/frames/TESTV001"
    assert [path.name for path in sorted(target.iterdir())] == [
        "TESTV001_frame_000001.jpg",
        "TESTV001_frame_000002.jpg",
    ]
    engine.dispose()
