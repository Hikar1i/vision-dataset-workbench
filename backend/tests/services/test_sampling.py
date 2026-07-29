import json

import pytest
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
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
from vision_dataset_workbench.sampling import SamplingInput
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.services.projects import ProjectForbidden
from vision_dataset_workbench.services.sampling import SamplingConflict, SamplingService


def make_service(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects" / "project-id").mkdir(parents=True)
    database_path = workspace / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    password_hash = hash_password("correct horse battery staple")
    with Session(engine) as session:
        for name in ("owner", "editor", "viewer"):
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
                    id="ready-id",
                    project_id="project-id",
                    short_code="READY001",
                    source_type="local",
                    title="ready",
                    status="ready",
                    duration=300,
                    fps=30,
                    total_frames=9000,
                    file_path="projects/project-id/videos/ready-id.mp4",
                ),
                Video(
                    id="pending-id",
                    project_id="project-id",
                    short_code="PEND0001",
                    source_type="local",
                    title="pending",
                    status="pending",
                ),
            ]
        )
        session.commit()
    actors = {}
    with Session(engine) as session:
        for name in ("owner", "editor", "viewer"):
            actor = session.get(User, f"{name}-id")
            assert actor is not None
            session.expunge(actor)
            actors[name] = actor
    service = SamplingService(
        engine, RuntimeSettings(home=home, workspace=workspace), workspace
    )
    return service, engine, workspace, actors


def test_editor_configures_batch_and_creates_persistent_extraction(tmp_path):
    service, engine, _workspace, actors = make_service(tmp_path)
    sampling_input = SamplingInput(
        "target_frames", {"minimum": 50, "maximum": 200}
    )

    batch = service.configure(
        actors["editor"],
        "project-id",
        ["ready-id", "pending-id"],
        sampling_input,
        "jpg",
        2,
    )

    assert len(batch.accepted) == 1
    assert batch.accepted[0].plan.expected_frames == 106
    summary = service.summaries(
        actors["viewer"], "project-id", ["ready-id"]
    )["ready-id"]
    assert summary.updated_at == batch.accepted[0].plan.updated_at
    assert batch.rejected[0].input == "pending-id"
    assert service.get_plan(actors["viewer"], "project-id", "ready-id") is not None
    with pytest.raises(ProjectForbidden):
        service.configure(
            actors["viewer"],
            "project-id",
            ["ready-id"],
            sampling_input,
            "jpg",
            2,
        )

    extraction = service.create_extractions(
        actors["owner"], "project-id", ["ready-id", "pending-id"]
    )
    assert len(extraction.accepted) == 1
    assert extraction.accepted[0].task.type == "extract_frames"
    assert json.loads(extraction.accepted[0].task.payload)["sampling_plan_version"] == 1
    assert extraction.rejected[0].input == "pending-id"

    conflict = service.create_extractions(
        actors["owner"], "project-id", ["ready-id"]
    )
    assert conflict.rejected[0].reason == "video already has an active task"
    engine.dispose()


def test_viewer_reads_frames_and_editor_filters_with_revision(tmp_path):
    service, engine, workspace, actors = make_service(tmp_path)
    frames_dir = workspace / "projects/project-id/frames/READY001"
    frames_dir.mkdir(parents=True)
    for sequence in (1, 2):
        (frames_dir / f"READY001_frame_{sequence:06d}.jpg").write_bytes(
            f"frame-{sequence}".encode()
        )
    with Session(engine) as session:
        session.add(
            SamplingPlan(
                id="plan-id",
                video_id="ready-id",
                mode="frame_interval",
                parameters='{"interval": 30}',
                output_format="jpg",
                output_quality=2,
                computed_interval=30,
                expected_frames=2,
                extracted_frames=2,
                enabled_frames=2,
                applied_version=1,
                generation=1,
                frame_revision=1,
            )
        )
        session.add_all(
            [
                Frame(
                    id=f"frame-{sequence}",
                    video_id="ready-id",
                    generation=1,
                    sequence=sequence,
                    source_frame_index=(sequence - 1) * 30,
                    time_offset=(sequence - 1),
                    file_path=(frames_dir / f"READY001_frame_{sequence:06d}.jpg")
                    .relative_to(workspace)
                    .as_posix(),
                )
                for sequence in (1, 2)
            ]
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

    frames, total, plan = service.list_frames(
        actors["viewer"], "project-id", "ready-id", page=1, page_size=1, enabled=None
    )
    frame, path = service.ready_frame_file(
        actors["viewer"], "project-id", "ready-id", frames[0].id
    )
    assert total == 2
    assert plan.frame_revision == 1
    assert frame.id == "frame-1"
    assert path.read_bytes() == b"frame-1"
    assert service.annotated_frame_ids(
        actors["viewer"], "project-id", "ready-id"
    ) == ["frame-1"]
    with pytest.raises(ProjectForbidden):
        service.set_frames_enabled(
            actors["viewer"],
            "project-id",
            "ready-id",
            {"frame-1": False},
            revision=1,
        )

    changed = service.set_frames_enabled(
        actors["editor"],
        "project-id",
        "ready-id",
        {"frame-1": False, "frame-2": True},
        revision=1,
    )
    assert changed.enabled_frames == 1
    assert changed.frame_revision == 2
    with pytest.raises(SamplingConflict):
        service.set_frames_enabled(
            actors["editor"],
            "project-id",
            "ready-id",
            {"frame-1": True},
            revision=1,
        )
    restored = service.set_frames_enabled(
        actors["editor"],
        "project-id",
        "ready-id",
        {"frame-1": True, "frame-2": True},
        revision=2,
    )
    assert restored.enabled_frames == 2
    engine.dispose()
