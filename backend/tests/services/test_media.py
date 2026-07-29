from datetime import datetime, timedelta

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.media import RemotePreview
from vision_dataset_workbench.models import Project, ProjectMembership, Task, User, Video
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.services.media import (
    MediaConflict,
    MediaNotFound,
    MediaService,
    MediaUnavailable,
)
from vision_dataset_workbench.services.projects import ProjectForbidden


def make_service(tmp_path, *, short_code_factory=None):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects" / "project-id").mkdir(parents=True)
    (home / "clips").mkdir()
    (home / "clips" / "one.mp4").write_bytes(b"one")
    (home / "clips" / "two.MKV").write_bytes(b"two")
    (home / "clips" / "notes.txt").write_text("ignore")
    (home / "clips" / "nested").mkdir()
    (home / "clips" / "nested" / "hidden.mp4").write_bytes(b"hidden")
    database_path = workspace / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    password_hash = hash_password("correct horse battery staple")
    with Session(engine) as session:
        users = [
            User(
                id=f"{name}-id",
                username=name,
                username_normalized=name,
                password_hash=password_hash,
                status="active",
            )
            for name in ("owner", "editor", "viewer", "outsider")
        ]
        session.add_all(users)
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
        session.commit()
    actors = {}
    with Session(engine) as session:
        for name in ("owner", "editor", "viewer", "outsider"):
            actor = session.get(User, f"{name}-id")
            assert actor is not None
            session.expunge(actor)
            actors[name] = actor

    previews = [
        RemotePreview(
            title="remote",
            url="https://example.test/video",
            duration=12,
            extractor="generic",
            external_id="remote-id",
        )
    ]
    settings = RuntimeSettings(home=home, workspace=workspace)
    kwargs = {"short_code_factory": short_code_factory} if short_code_factory else {}
    service = MediaService(
        engine, settings, workspace, previewer=lambda *_: previews, **kwargs
    )
    return service, engine, actors


def test_local_preview_is_first_level_and_editor_imports(tmp_path):
    service, engine, actors = make_service(tmp_path)

    preview = service.preview_local(actors["editor"], "project-id", "clips")
    batch = service.import_local(
        actors["editor"], "project-id", ["clips/one.mp4", "clips/two.MKV"]
    )

    assert [item.path for item in preview] == ["clips/one.mp4", "clips/two.MKV"]
    assert len(batch.accepted) == 2
    assert batch.accepted[0].task.status == "queued"
    assert batch.rejected == []
    videos, total = service.list_videos(
        actors["viewer"], "project-id", page=1, page_size=50
    )
    assert total == 2
    assert {video.title for video in videos} == {"one", "two"}
    engine.dispose()


def test_import_assigns_short_code_and_retries_project_collision(tmp_path):
    codes = iter(("7K3M9Q2X", "7K3M9Q2X", "8M4N0R3Y"))
    service, engine, actors = make_service(
        tmp_path, short_code_factory=lambda: next(codes)
    )

    first = service.import_local(
        actors["owner"], "project-id", ["clips/one.mp4"]
    ).accepted[0].video
    second = service.import_local(
        actors["owner"], "project-id", ["clips/two.MKV"]
    ).accepted[0].video

    assert first.short_code == "7K3M9Q2X"
    assert second.short_code == "8M4N0R3Y"
    assert first.id != second.id
    engine.dispose()


def test_import_fails_safely_after_five_short_code_collisions(tmp_path):
    service, engine, actors = make_service(
        tmp_path, short_code_factory=lambda: "7K3M9Q2X"
    )
    service.import_local(actors["owner"], "project-id", ["clips/one.mp4"])

    with pytest.raises(MediaUnavailable, match="temporarily unavailable"):
        service.import_local(actors["owner"], "project-id", ["clips/two.MKV"])

    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Video)) == 1
        assert session.scalar(select(func.count()).select_from(Task)) == 1
    engine.dispose()


def test_import_does_not_retry_other_integrity_errors(tmp_path):
    calls = 0

    def invalid_code() -> str:
        nonlocal calls
        calls += 1
        return "invalid!"

    service, engine, actors = make_service(
        tmp_path, short_code_factory=invalid_code
    )

    with pytest.raises(IntegrityError):
        service.import_local(actors["owner"], "project-id", ["clips/one.mp4"])

    assert calls == 1
    engine.dispose()


def test_viewer_cannot_import_but_can_list_tasks(tmp_path):
    service, engine, actors = make_service(tmp_path)

    with pytest.raises(ProjectForbidden):
        service.preview_local(actors["viewer"], "project-id", "clips")
    with pytest.raises(ProjectForbidden):
        service.import_remote(
            actors["viewer"], "project-id", [("remote", "https://example.test/video")]
        )

    service.import_local(actors["owner"], "project-id", ["clips/one.mp4"])
    tasks, total = service.list_tasks(
        actors["viewer"], "project-id", page=1, page_size=50
    )
    assert total == 1
    assert tasks[0].type == "copy_video"
    engine.dispose()


def test_visible_tasks_follow_project_permissions(tmp_path):
    service, engine, actors = make_service(tmp_path)
    older = datetime(2026, 7, 24, 8, 0, 0)
    newer = datetime(2026, 7, 24, 9, 0, 0)
    with Session(engine) as session:
        session.add(Project(id="hidden-project", name="hidden", creator_id="outsider-id"))
        session.add_all(
            [
                Task(
                    id="older-task",
                    project_id="project-id",
                    submitted_by_id="owner-id",
                    type="copy_video",
                    status="queued",
                    created_at=older,
                    updated_at=older,
                ),
                Task(
                    id="newer-task",
                    project_id="project-id",
                    submitted_by_id="owner-id",
                    type="copy_video",
                    status="failed",
                    created_at=newer,
                    updated_at=newer,
                ),
                Task(
                    id="hidden-task",
                    project_id="hidden-project",
                    submitted_by_id="outsider-id",
                    type="copy_video",
                    status="succeeded",
                    created_at=newer + timedelta(hours=1),
                    updated_at=newer + timedelta(hours=1),
                ),
            ]
        )
        session.commit()

    for role, can_manage in (("owner", True), ("editor", True), ("viewer", False)):
        items, total, latest_terminal_at = service.list_visible_tasks(
            actors[role], page=1, page_size=20
        )
        assert total == 2
        assert [item.task.id for item in items] == ["newer-task", "older-task"]
        assert all(item.project_name == "project" for item in items)
        assert all(item.can_manage is can_manage for item in items)
        assert latest_terminal_at == newer

    assert service.list_visible_tasks(
        actors["outsider"], page=1, page_size=20
    )[0][0].task.id == "hidden-task"
    engine.dispose()


def test_remote_preview_import_cancel_and_retry(tmp_path):
    service, engine, actors = make_service(tmp_path)

    preview = service.preview_remote(
        actors["owner"], "project-id", "https://example.test/video"
    )
    batch = service.import_remote(
        actors["owner"], "project-id", [(preview[0].title, preview[0].url)]
    )
    task = batch.accepted[0].task
    canceled = service.cancel_task(actors["editor"], "project-id", task.id)
    retried = service.retry_task(actors["owner"], "project-id", task.id)

    assert canceled.status == "canceled"
    assert retried.status == "queued"
    assert retried.retry_of_id == task.id
    with pytest.raises(MediaConflict):
        service.retry_task(actors["owner"], "project-id", retried.id)
    engine.dispose()


def test_import_only_accepts_remaining_project_capacity(tmp_path):
    service, engine, actors = make_service(tmp_path)
    with Session(engine) as session:
        session.add_all(
            [
                Video(
                    id=f"existing-{index}",
                    project_id="project-id",
                    source_type="local",
                    title=f"existing {index}",
                )
                for index in range(998)
            ]
        )
        session.commit()

    batch = service.import_local(
        actors["editor"], "project-id", ["clips/one.mp4", "clips/two.MKV"]
    )

    assert len(batch.accepted) == 1
    assert batch.accepted[0].video.title == "one"
    assert batch.skipped == []
    assert len(batch.rejected) == 1
    assert batch.rejected[0].input == "clips/two.MKV"
    assert "999" in batch.rejected[0].reason
    _, total = service.list_videos(
        actors["viewer"], "project-id", page=1, page_size=999
    )
    assert total == 999
    engine.dispose()


def test_editor_updates_video_enabled_with_optimistic_lock(tmp_path):
    service, engine, actors = make_service(tmp_path)
    imported = service.import_local(
        actors["owner"], "project-id", ["clips/one.mp4"]
    ).accepted[0].video

    disabled = service.update_enabled(
        actors["editor"],
        "project-id",
        imported.id,
        enabled=False,
        version=imported.version,
    )

    assert disabled.enabled is False
    assert disabled.version == imported.version + 1
    with pytest.raises(MediaConflict, match="version"):
        service.update_enabled(
            actors["owner"],
            "project-id",
            imported.id,
            enabled=True,
            version=imported.version,
        )
    with pytest.raises(ProjectForbidden):
        service.update_enabled(
            actors["viewer"],
            "project-id",
            imported.id,
            enabled=True,
            version=disabled.version,
        )
    engine.dispose()


def test_video_enabled_update_rejects_cross_project_video(tmp_path):
    service, engine, actors = make_service(tmp_path)
    imported = service.import_local(
        actors["owner"], "project-id", ["clips/one.mp4"]
    ).accepted[0].video
    with Session(engine) as session:
        session.add(Project(id="other-project", name="other", creator_id="owner-id"))
        session.commit()

    with pytest.raises(MediaNotFound):
        service.update_enabled(
            actors["owner"],
            "other-project",
            imported.id,
            enabled=False,
            version=imported.version,
        )
    engine.dispose()


def test_latest_tasks_returns_one_latest_task_per_video(tmp_path):
    service, engine, actors = make_service(tmp_path)
    batch = service.import_local(
        actors["owner"], "project-id", ["clips/one.mp4", "clips/two.MKV"]
    )
    first, second = batch.accepted
    with Session(engine) as session:
        first_task = session.get(Task, first.task.id)
        second_task = session.get(Task, second.task.id)
        assert first_task is not None
        assert second_task is not None
        first_task.status = "succeeded"
        first_task.updated_at = first_task.updated_at + timedelta(seconds=1)
        second_task.status = "succeeded"
        session.flush()
        latest = Task(
            id="latest-first-task",
            project_id="project-id",
            submitted_by_id="owner-id",
            video_id=first.video.id,
            type="copy_video",
            status="failed",
            error="copy failed",
            created_at=first_task.created_at + timedelta(seconds=2),
            updated_at=first_task.updated_at + timedelta(seconds=2),
        )
        session.add(latest)
        session.commit()

    tasks = service.latest_tasks(
        actors["viewer"], "project-id", [first.video.id, second.video.id]
    )

    assert tasks[first.video.id].id == "latest-first-task"
    assert tasks[second.video.id].id == second.task.id
    assert service.latest_tasks(actors["viewer"], "project-id", []) == {}
    engine.dispose()
