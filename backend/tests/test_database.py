from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from vision_dataset_workbench.database import (
    create_workspace_database,
    database_url,
    make_engine,
    sqlite_supports_safe_wal,
)
from vision_dataset_workbench.models import (
    AuthSession,
    Frame,
    Project,
    ProjectMembership,
    SamplingPlan,
    Task,
    User,
    Video,
)
from vision_dataset_workbench.security.passwords import hash_password, verify_password


def test_migration_creates_users_and_password_hash_round_trips(tmp_path):
    database_path = tmp_path / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)

    assert {
        "users",
        "sessions",
        "projects",
        "project_memberships",
        "videos",
        "tasks",
        "sampling_plans",
        "frames",
    }.issubset(
        inspect(engine).get_table_names()
    )
    assert AuthSession.__tablename__ == "sessions"
    with engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
    assert journal_mode == ("wal" if sqlite_supports_safe_wal() else "delete")
    password_hash = hash_password("correct horse battery staple")
    with Session(engine) as session:
        session.add(
            User(
                username="Admin",
                username_normalized="admin",
                password_hash=password_hash,
                is_system_admin=True,
            )
        )
        session.commit()
        user = session.scalar(select(User).where(User.username_normalized == "admin"))

    assert user is not None
    assert user.username == "Admin"
    assert verify_password(user.password_hash, "correct horse battery staple")

    with Session(engine) as session:
        session.add(
            User(
                username="admin",
                username_normalized="admin",
                password_hash=password_hash,
                is_system_admin=False,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_projects_allow_duplicate_names_and_memberships_are_unique(tmp_path):
    database_path = tmp_path / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    password_hash = hash_password("correct horse battery staple")
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    id="owner-id",
                    username="owner",
                    username_normalized="owner",
                    password_hash=password_hash,
                ),
                User(
                    id="member-id",
                    username="member",
                    username_normalized="member",
                    password_hash=password_hash,
                ),
            ]
        )
        session.flush()
        session.add_all(
            [
                Project(id="project-1", name="same name", creator_id="owner-id"),
                Project(id="project-2", name="same name", creator_id="owner-id"),
            ]
        )
        session.add(
            ProjectMembership(
                project_id="project-1", user_id="member-id", role="editor"
            )
        )
        session.commit()

    with Session(engine) as session:
        session.add(
            ProjectMembership(
                project_id="project-1", user_id="member-id", role="viewer"
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

    with Session(engine) as session:
        session.add(
            ProjectMembership(
                project_id="project-2", user_id="member-id", role="owner"
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_video_identities_and_active_tasks_are_unique_per_project(tmp_path):
    database_path = tmp_path / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    password_hash = hash_password("correct horse battery staple")
    with Session(engine) as session:
        session.add(
            User(
                id="owner-id",
                username="owner",
                username_normalized="owner",
                password_hash=password_hash,
            )
        )
        session.flush()
        session.add(Project(id="project-1", name="project", creator_id="owner-id"))
        session.commit()

        local = Video(
            id="local-1",
            project_id="project-1",
            source_type="local",
            title="local",
            content_sha256="a" * 64,
        )
        remote = Video(
            id="remote-1",
            project_id="project-1",
            source_type="remote",
            title="remote",
            extractor="youtube",
            external_id="remote-id",
        )
        session.add_all([local, remote])
        session.commit()

    for duplicate in (
        Video(
            project_id="project-1",
            source_type="local",
            title="duplicate local",
            content_sha256="a" * 64,
        ),
        Video(
            project_id="project-1",
            source_type="remote",
            title="duplicate remote",
            extractor="youtube",
            external_id="remote-id",
        ),
    ):
        with Session(engine) as session:
            session.add(duplicate)
            with pytest.raises(IntegrityError):
                session.commit()

    with Session(engine) as session:
        session.add(
            Task(
                id="task-1",
                project_id="project-1",
                submitted_by_id="owner-id",
                video_id="local-1",
                type="copy_video",
            )
        )
        session.commit()

    with Session(engine) as session:
        session.add(
            Task(
                project_id="project-1",
                submitted_by_id="owner-id",
                video_id="local-1",
                type="copy_video",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_sampling_plan_frames_and_extraction_task_constraints(tmp_path):
    database_path = tmp_path / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    with Session(engine) as session:
        session.add(
            User(
                id="owner-id",
                username="owner",
                username_normalized="owner",
                password_hash="hash",
            )
        )
        session.flush()
        session.add(Project(id="project-id", name="project", creator_id="owner-id"))
        session.flush()
        session.add(
            Video(
                id="video-id",
                project_id="project-id",
                source_type="local",
                title="video",
                status="ready",
            )
        )
        session.flush()
        session.add(
            SamplingPlan(
                id="plan-id",
                video_id="video-id",
                mode="target_frames",
                parameters='{"minimum": 50, "maximum": 200}',
                output_format="jpg",
                output_quality=2,
                expected_frames=50,
            )
        )
        session.add_all(
            [
                Frame(
                    id="frame-1",
                    video_id="video-id",
                    generation=1,
                    sequence=1,
                    source_frame_index=0,
                    time_offset=0,
                    file_path="projects/project-id/frames/video-id/000001.jpg",
                ),
                Task(
                    id="extract-id",
                    project_id="project-id",
                    submitted_by_id="owner-id",
                    video_id="video-id",
                    type="extract_frames",
                ),
            ]
        )
        session.commit()

    with Session(engine) as session:
        session.add(
            SamplingPlan(
                video_id="video-id",
                mode="target_frames",
                parameters="{}",
                output_format="jpg",
                output_quality=2,
                expected_frames=10,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

    with Session(engine) as session:
        session.add(
            Frame(
                video_id="video-id",
                generation=2,
                sequence=1,
                source_frame_index=1,
                time_offset=0.04,
                file_path="projects/project-id/frames/video-id/duplicate.jpg",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_authentication_migration_backfills_existing_administrator(tmp_path, monkeypatch):
    database_path = tmp_path / "db" / "workbench.sqlite3"
    database_path.parent.mkdir(parents=True)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    monkeypatch.setenv(
        "VDW_DATABASE_URL", database_url(database_path).render_as_string(hide_password=False)
    )
    command.upgrade(config, "0001_initial")
    engine = make_engine(database_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO users
                (id, username, password_hash, status, is_system_admin, created_at)
            VALUES
                (?, ?, ?, ?, ?, ?)
            """,
            ("admin-id", "Admin", "hash", "active", True, "2026-07-23 00:00:00.000000"),
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = make_engine(database_path)
    with Session(engine) as session:
        admin = session.get(User, "admin-id")
    assert admin is not None
    assert admin.username_normalized == "admin"
    assert admin.updated_at == admin.created_at
    assert {"projects", "project_memberships"}.issubset(
        inspect(engine).get_table_names()
    )
    engine.dispose()
