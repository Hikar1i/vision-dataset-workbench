from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import Project, User, Video
from vision_dataset_workbench.security.passwords import hash_password

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


def test_overview_uses_current_project_schema(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    database_path = workspace / "db/workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    with Session(engine) as database:
        database.add(
            User(
                id="owner-id",
                username="owner",
                username_normalized="owner",
                password_hash=hash_password(PASSWORD),
                status="active",
            )
        )
        database.flush()
        database.add(Project(id="project-id", name="project", creator_id="owner-id"))
        database.flush()
        database.add(
            Video(
                id="video-id",
                project_id="project-id",
                short_code="TESTV001",
                source_type="local",
                title="video",
                status="ready",
            )
        )
        database.commit()
    engine.dispose()

    app = create_app(RuntimeSettings(home=home, workspace=workspace))
    client = TestClient(app)
    assert client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": "owner", "password": PASSWORD},
    ).status_code == 200

    response = client.get("/api/v1/overview")

    assert response.status_code == 200
    assert response.json()["projects"] == 1
    assert response.json()["videos"] == 1
