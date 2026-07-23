import pytest
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.media import RemotePreview
from vision_dataset_workbench.models import Project, ProjectMembership, User
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.services.media import MediaConflict, MediaService
from vision_dataset_workbench.services.projects import ProjectForbidden


def make_service(tmp_path):
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
    service = MediaService(engine, settings, workspace, previewer=lambda *_: previews)
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
