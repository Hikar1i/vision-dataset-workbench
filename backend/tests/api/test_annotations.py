from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import Frame, SamplingPlan, Task, User, Video
from vision_dataset_workbench.security.passwords import hash_password

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


def make_app(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects").mkdir(parents=True)
    database_path = workspace / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    password_hash = hash_password(PASSWORD)
    with Session(engine) as session:
        for username in ("creator", "editor", "viewer", "outsider"):
            session.add(
                User(
                    id=f"{username}-id",
                    username=username,
                    username_normalized=username,
                    password_hash=password_hash,
                    status="active",
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


def seed_annotation_context(app, owner: TestClient):
    project = owner.post(
        "/api/v1/projects",
        headers=ORIGIN,
        json={"name": "Project", "description": ""},
    ).json()
    project_id = project["id"]
    for username, role in (("editor", "editor"), ("viewer", "viewer")):
        response = owner.post(
            f"/api/v1/projects/{project_id}/members",
            headers=ORIGIN,
            json={"username": username, "role": role},
        )
        assert response.status_code == 201
    label = owner.post(
        f"/api/v1/projects/{project_id}/labels",
        headers=ORIGIN,
        json={"name": "helmet", "description_zh": "安全帽", "color": "#16866f"},
    ).json()
    with Session(app.state.auth_service.engine) as session:
        session.add(
            Video(
                id="video-id",
                project_id=project_id,
                source_type="local",
                title="video",
                status="ready",
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
                parameters='{"minimum": 10, "maximum": 100}',
                output_format="jpg",
                output_quality=2,
                expected_frames=1,
                extracted_frames=1,
                enabled_frames=1,
            )
        )
        session.add(
            Frame(
                id="frame-id",
                video_id="video-id",
                generation=1,
                sequence=1,
                source_frame_index=0,
                time_offset=0,
                file_path=f"projects/{project_id}/frames/video-id/000001.jpg",
            )
        )
        session.commit()
    return project_id, label["id"]


def annotation_url(project_id: str) -> str:
    return (
        f"/api/v1/projects/{project_id}/videos/video-id/frames/frame-id/annotations"
    )


def box(label_id: str, *, annotation_id: str = "box-id") -> dict[str, object]:
    return {
        "id": annotation_id,
        "label_id": label_id,
        "x_min": 10,
        "y_min": 20,
        "x_max": 110,
        "y_max": 220,
        "source": "manual",
        "confidence": None,
    }


def test_editor_replaces_and_clears_a_whole_frame(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "creator")
    editor = client_for(app, "editor")
    project_id, label_id = seed_annotation_context(app, owner)
    url = annotation_url(project_id)

    initial = editor.get(url)
    assert initial.status_code == 200
    assert initial.json() == {
        "frame_id": "frame-id",
        "annotation_revision": 1,
        "items": [],
    }

    saved = editor.put(
        url,
        headers=ORIGIN,
        json={"annotation_revision": 1, "items": [box(label_id)]},
    )
    assert saved.status_code == 200
    assert saved.json()["annotation_revision"] == 2
    assert saved.json()["items"] == [box(label_id)]

    stale = owner.put(
        url,
        headers=ORIGIN,
        json={"annotation_revision": 1, "items": []},
    )
    assert stale.status_code == 409

    cleared = owner.put(
        url,
        headers=ORIGIN,
        json={"annotation_revision": 2, "items": []},
    )
    assert cleared.status_code == 200
    assert cleared.json()["annotation_revision"] == 3
    assert cleared.json()["items"] == []


def test_viewer_reads_but_cannot_write_and_outsider_cannot_read(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "creator")
    viewer = client_for(app, "viewer")
    outsider = client_for(app, "outsider")
    project_id, label_id = seed_annotation_context(app, owner)
    url = annotation_url(project_id)

    assert viewer.get(url).status_code == 200
    assert viewer.put(
        url,
        headers=ORIGIN,
        json={"annotation_revision": 1, "items": [box(label_id)]},
    ).status_code == 403
    assert outsider.get(url).status_code == 404


def test_annotation_validation_rejects_bad_bounds_labels_and_ids(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "creator")
    project_id, label_id = seed_annotation_context(app, owner)
    url = annotation_url(project_id)

    outside = box(label_id)
    outside["x_max"] = 1921
    assert owner.put(
        url,
        headers=ORIGIN,
        json={"annotation_revision": 1, "items": [outside]},
    ).status_code == 422
    assert owner.put(
        url,
        headers=ORIGIN,
        json={"annotation_revision": 1, "items": [box("unknown-label")]},
    ).status_code == 422
    assert owner.put(
        url,
        headers=ORIGIN,
        json={
            "annotation_revision": 1,
            "items": [box(label_id), box(label_id)],
        },
    ).status_code == 422


def test_annotation_write_requires_same_origin(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "creator")
    project_id, _label_id = seed_annotation_context(app, owner)

    assert owner.put(
        annotation_url(project_id),
        json={"annotation_revision": 1, "items": []},
    ).status_code == 403


def test_manual_save_is_blocked_while_batch_auto_annotation_is_active(tmp_path):
    app = make_app(tmp_path)
    owner = client_for(app, "creator")
    project_id, _label_id = seed_annotation_context(app, owner)
    with Session(app.state.auth_service.engine) as session:
        session.add(
            Task(
                project_id=project_id,
                submitted_by_id="creator-id",
                video_id="video-id",
                type="auto_annotate",
                status="running",
            )
        )
        session.commit()

    response = owner.put(
        annotation_url(project_id),
        headers=ORIGIN,
        json={"annotation_revision": 1, "items": []},
    )

    assert response.status_code == 409
