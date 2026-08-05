from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.media import RemotePreview
from vision_dataset_workbench.models import Project, ProjectMembership, User, Video
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.services.media import MediaService

PASSWORD = "correct horse battery staple"
ORIGIN = {"Origin": "http://testserver"}


def make_app(tmp_path, *, short_code_factory=None):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects" / "project-id").mkdir(parents=True)
    (home / "clips").mkdir()
    (home / "clips" / "one.mp4").write_bytes(b"one")
    database_path = workspace / "db" / "workbench.sqlite3"
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
            ]
        )
        session.commit()
    engine.dispose()
    settings = RuntimeSettings(home=home, workspace=workspace)
    app = create_app(settings)
    kwargs = {"short_code_factory": short_code_factory} if short_code_factory else {}
    app.state.media_service = MediaService(
        app.state.auth_service.engine,
        settings,
        workspace,
        previewer=lambda *_: [
            RemotePreview(
                title="remote",
                url="https://example.test/video",
                duration=2,
                extractor="generic",
                external_id="remote-id",
            )
        ],
        **kwargs,
    )
    return app


def client_for(app, username):
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/login",
            headers=ORIGIN,
            json={"username": username, "password": PASSWORD},
        ).status_code
        == 200
    )
    return client


def test_editor_imports_and_viewer_reads_but_cannot_write(tmp_path):
    app = make_app(tmp_path)
    editor = client_for(app, "editor")
    viewer = client_for(app, "viewer")

    preview = editor.post(
        "/api/v1/projects/project-id/imports/local/preview",
        headers=ORIGIN,
        json={"path": "clips"},
    )
    imported = editor.post(
        "/api/v1/projects/project-id/imports/local",
        headers=ORIGIN,
        json={"paths": ["clips/one.mp4"]},
    )

    assert preview.status_code == 200
    assert preview.json()[0]["path"] == "clips/one.mp4"
    assert imported.status_code == 202
    assert len(imported.json()["accepted"]) == 1
    short_code = imported.json()["accepted"][0]["video"]["short_code"]
    assert len(short_code) == 8
    listed = viewer.get("/api/v1/projects/project-id/videos?page_size=999")
    assert listed.status_code == 200
    assert listed.json()["total"] == 1
    assert listed.json()["items"][0]["enabled"] is True
    assert listed.json()["items"][0]["short_code"] == short_code
    assert listed.json()["items"][0]["latest_task"]["status"] == "queued"
    assert (
        viewer.get("/api/v1/projects/project-id/videos?page_size=1000").status_code
        == 422
    )
    assert viewer.get("/api/v1/projects/project-id/tasks").json()["total"] == 1
    assert (
        viewer.post(
            "/api/v1/projects/project-id/imports/remote",
            headers=ORIGIN,
            json={"items": [{"title": "x", "url": "https://example.test/x"}]},
        ).status_code
        == 403
    )


def test_short_code_exhaustion_returns_503_for_local_and_remote_imports(tmp_path):
    app = make_app(tmp_path, short_code_factory=lambda: "7K3M9Q2X")
    with Session(app.state.auth_service.engine) as session:
        session.add(
            Video(
                id="existing-video",
                project_id="project-id",
                short_code="7K3M9Q2X",
                source_type="local",
                title="existing",
            )
        )
        session.commit()
    owner = client_for(app, "owner")

    local_response = owner.post(
        "/api/v1/projects/project-id/imports/local",
        headers=ORIGIN,
        json={"paths": ["clips/one.mp4"]},
    )
    remote_response = owner.post(
        "/api/v1/projects/project-id/imports/remote",
        headers=ORIGIN,
        json={"items": [{"title": "remote", "url": "https://example.test/video"}]},
    )

    for response in (local_response, remote_response):
        assert response.status_code == 503
        assert response.json()["detail"] == (
            "video short code allocation temporarily unavailable"
        )


def test_global_tasks_include_project_context_and_permissions(tmp_path):
    app = make_app(tmp_path)
    assert TestClient(app).get("/api/v1/tasks").status_code == 401
    owner = client_for(app, "owner")
    editor = client_for(app, "editor")
    viewer = client_for(app, "viewer")
    outsider = client_for(app, "outsider")
    imported = owner.post(
        "/api/v1/projects/project-id/imports/local",
        headers=ORIGIN,
        json={"paths": ["clips/one.mp4"]},
    ).json()

    viewer_page = viewer.get("/api/v1/tasks?page=1&page_size=50")
    editor_page = editor.get("/api/v1/tasks")

    assert viewer_page.status_code == 200
    assert viewer_page.json()["items"] == [
        {
                **imported["accepted"][0]["task"],
                "project_id": "project-id",
                "model_project_id": None,
                "project_name": "project",
                "resource_kind": "project",
                "resource_name": "project",
                "can_manage": False,
        }
    ]
    assert viewer_page.json()["latest_terminal_at"] is None
    assert editor_page.json()["items"][0]["can_manage"] is True
    assert outsider.get("/api/v1/tasks").json()["total"] == 0


def test_editor_updates_video_enabled_and_viewer_is_read_only(tmp_path):
    app = make_app(tmp_path)
    editor = client_for(app, "editor")
    viewer = client_for(app, "viewer")
    imported = editor.post(
        "/api/v1/projects/project-id/imports/local",
        headers=ORIGIN,
        json={"paths": ["clips/one.mp4"]},
    ).json()
    video = imported["accepted"][0]["video"]
    endpoint = f"/api/v1/projects/project-id/videos/{video['id']}/enabled"

    forbidden = viewer.put(
        endpoint,
        headers=ORIGIN,
        json={"enabled": False, "version": video["version"]},
    )
    disabled = editor.put(
        endpoint,
        headers=ORIGIN,
        json={"enabled": False, "version": video["version"]},
    )
    conflict = editor.put(
        endpoint,
        headers=ORIGIN,
        json={"enabled": True, "version": video["version"]},
    )

    assert forbidden.status_code == 403
    assert disabled.status_code == 200
    assert disabled.json()["enabled"] is False
    assert disabled.json()["version"] == video["version"] + 1
    assert conflict.status_code == 409


def test_remote_preview_cancel_retry_and_same_origin(tmp_path):
    owner = client_for(make_app(tmp_path), "owner")

    preview = owner.post(
        "/api/v1/projects/project-id/imports/remote/preview",
        headers=ORIGIN,
        json={"url": "https://example.test/video"},
    )
    assert preview.json()[0]["external_id"] == "remote-id"
    assert (
        owner.post(
            "/api/v1/projects/project-id/imports/remote",
            json={"items": [{"title": "x", "url": "https://example.test/x"}]},
        ).status_code
        == 403
    )
    imported = owner.post(
        "/api/v1/projects/project-id/imports/remote",
        headers=ORIGIN,
        json={"items": [{"title": "remote", "url": "https://example.test/video"}]},
    )
    task_id = imported.json()["accepted"][0]["task"]["id"]
    canceled = owner.post(
        f"/api/v1/projects/project-id/tasks/{task_id}/cancel", headers=ORIGIN
    )
    retried = owner.post(
        f"/api/v1/projects/project-id/tasks/{task_id}/retry", headers=ORIGIN
    )
    assert canceled.json()["status"] == "canceled"
    assert retried.status_code == 201
    assert retried.json()["retry_of_id"] == task_id


def test_members_stream_download_and_thumbnail_with_range(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "owner")
    viewer = client_for(app, "viewer")
    outsider = client_for(app, "outsider")
    imported = owner.post(
        "/api/v1/projects/project-id/imports/local",
        headers=ORIGIN,
        json={"paths": ["clips/one.mp4"]},
    ).json()
    imported_video = imported["accepted"][0]["video"]
    video_id = imported_video["id"]
    short_code = imported_video["short_code"]
    video_path = app.state.workspace / f"projects/project-id/videos/{short_code}.mp4"
    thumbnail_path = (
        app.state.workspace
        / f"projects/project-id/thumbnails/{short_code}_thumbnail.jpg"
    )
    video_path.parent.mkdir(parents=True, exist_ok=True)
    thumbnail_path.parent.mkdir(parents=True, exist_ok=True)
    video_path.write_bytes(b"0123456789")
    thumbnail_path.write_bytes(b"jpeg")
    with Session(app.state.auth_service.engine) as session:
        video = session.get(Video, video_id)
        assert video is not None
        video.status = "ready"
        video.file_path = video_path.relative_to(app.state.workspace).as_posix()
        video.thumbnail_path = thumbnail_path.relative_to(app.state.workspace).as_posix()
        session.commit()

    ranged = viewer.get(
        f"/api/v1/projects/project-id/videos/{video_id}/content",
        headers={"Range": "bytes=2-5"},
    )
    downloaded = viewer.get(
        f"/api/v1/projects/project-id/videos/{video_id}/download"
    )
    thumbnail = viewer.get(
        f"/api/v1/projects/project-id/videos/{video_id}/thumbnail"
    )

    assert ranged.status_code == 206
    assert ranged.content == b"2345"
    assert ranged.headers["content-range"] == "bytes 2-5/10"
    assert downloaded.status_code == 200
    assert "attachment" in downloaded.headers["content-disposition"]
    assert thumbnail.content == b"jpeg"
    assert (
        outsider.get(
            f"/api/v1/projects/project-id/videos/{video_id}/content"
        ).status_code
        == 404
    )


def test_pending_video_cannot_be_streamed(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "owner")
    imported = owner.post(
        "/api/v1/projects/project-id/imports/local",
        headers=ORIGIN,
        json={"paths": ["clips/one.mp4"]},
    ).json()
    video_id = imported["accepted"][0]["video"]["id"]

    assert (
        owner.get(
            f"/api/v1/projects/project-id/videos/{video_id}/content"
        ).status_code
        == 409
    )
