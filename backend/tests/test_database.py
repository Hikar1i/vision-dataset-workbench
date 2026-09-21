from datetime import datetime
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
    DatasetExport,
    Frame,
    FrameAnnotation,
    InferenceModel,
    ModelProject,
    ModelProjectMembership,
    OFFICIAL_YOLO11_MODEL_PROJECT_ID,
    OFFICIAL_YOLO11_MODEL_PROJECT_NAME,
    OFFICIAL_YOLO11_SYSTEM_KEY,
    Project,
    ProjectLabel,
    ProjectMembership,
    SamplingPlan,
    Task,
    TrainingTask,
    User,
    UserXAnyLabelingSetting,
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
        "labels",
        "project_memberships",
        "model_project_memberships",
        "videos",
        "tasks",
        "sampling_plans",
        "frames",
        "annotations",
        "inference_models",
        "model_projects",
        "user_xanylabeling_settings",
        "dataset_exports",
        "training_preparations",
        "model_artifacts",
        "model_inference_runs",
        "evaluation_datasets",
        "model_evaluations",
        "gpu_leases",
    }.issubset(
        inspect(engine).get_table_names()
    )
    artifact_indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspect(engine).get_indexes("model_artifacts")
    }
    inference_indexes = {
        index["name"]: tuple(index["column_names"])
        for index in inspect(engine).get_indexes("model_inference_runs")
    }
    assert artifact_indexes["uq_model_artifacts_active_format"] == (
        "model_id",
        "format",
    )
    assert inference_indexes["uq_model_inference_runs_active_session"] == (
        "model_id",
        "created_by_id",
    )
    assert {"default_dataset_mode", "default_multi_dataset_config"} <= {
        column["name"] for column in inspect(engine).get_columns("training_tasks")
    }
    assert {"dataset_mode", "multi_dataset_config"} <= {
        column["name"] for column in inspect(engine).get_columns("training_models")
    }
    user_columns = {
        column["name"] for column in inspect(engine).get_columns("users")
    }
    assert "must_change_password" in user_columns
    assert {"reviewed_at", "reviewed_by_id"}.isdisjoint(user_columns)
    assert AuthSession.__tablename__ == "sessions"
    with Session(engine) as session:
        official = session.get(ModelProject, OFFICIAL_YOLO11_MODEL_PROJECT_ID)
        assert official is not None
        assert official.name == OFFICIAL_YOLO11_MODEL_PROJECT_NAME
        assert official.system_key == OFFICIAL_YOLO11_SYSTEM_KEY
        assert official.created_by_id is None
    video_columns = {
        column["name"]: column for column in inspect(engine).get_columns("videos")
    }
    assert video_columns["short_code"]["nullable"] is False
    frame_indexes = {index["name"] for index in inspect(engine).get_indexes("frames")}
    assert "uq_frames_video_sequence" in frame_indexes
    assert "ix_frames_video_id" not in frame_indexes
    assert "ix_frames_enabled" not in frame_indexes
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


def test_resource_activity_migration_advances_stale_parent_timestamps(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "db" / "workbench.sqlite3"
    database_path.parent.mkdir(parents=True)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    monkeypatch.setenv(
        "VDW_DATABASE_URL", database_url(database_path).render_as_string(hide_password=False)
    )
    command.upgrade(config, "0027_official_model_project")
    engine = make_engine(database_path)
    old = datetime(2026, 1, 1)
    dataset_activity = datetime(2026, 2, 1)
    model_activity = datetime(2026, 3, 1)
    with Session(engine) as session:
        session.add(
            User(
                id="activity-owner",
                username="activity-owner",
                username_normalized="activity-owner",
                password_hash="hash",
                created_at=old,
                updated_at=old,
            )
        )
        session.flush()
        session.add(
            Project(
                id="activity-project",
                name="activity-project",
                creator_id="activity-owner",
                created_at=old,
                updated_at=old,
            )
        )
        session.add(
            ModelProject(
                id="activity-model-project",
                name="activity-model-project",
                name_normalized="activity-model-project",
                series_type="archive",
                created_by_id="activity-owner",
                created_at=old,
                updated_at=old,
            )
        )
        session.flush()
        session.add(
            Video(
                id="activity-video",
                project_id="activity-project",
                short_code="ABCDEFGH",
                source_type="local",
                title="activity-video",
                status="ready",
                created_at=dataset_activity,
                updated_at=dataset_activity,
            )
        )
        session.add(
            InferenceModel(
                id="activity-model",
                model_project_id="activity-model-project",
                model_code="activity-model",
                name="activity-model",
                kind="yolo",
                status="ready",
                source_name="activity.pt",
                created_by_id="activity-owner",
                created_at=model_activity,
                updated_at=model_activity,
            )
        )
        session.commit()
    engine.dispose()

    command.upgrade(config, "head")

    engine = make_engine(database_path)
    with Session(engine) as session:
        assert session.get(Project, "activity-project").updated_at == dataset_activity
        assert (
            session.get(ModelProject, "activity-model-project").updated_at
            == model_activity
        )
    engine.dispose()


def test_access_control_migration_converts_accounts_and_backfills_training_projects(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "workbench.sqlite3"
    monkeypatch.setenv(
        "VDW_DATABASE_URL",
        database_url(database_path).render_as_string(hide_password=False),
    )
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "0025_model_operations")
    engine = make_engine(database_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users "
            "(id, username, username_normalized, password_hash, status, "
            "is_system_admin, created_at, updated_at) VALUES (?, ?, ?, 'hash', ?, ?, ?, ?)",
            [
                ("admin-id", "admin", "admin", "active", True, "2026-09-20", "2026-09-20"),
                ("pending-id", "pending", "pending", "pending", False, "2026-09-20", "2026-09-20"),
                ("rejected-id", "rejected", "rejected", "rejected", False, "2026-09-20", "2026-09-20"),
            ],
        )
        connection.exec_driver_sql(
            "INSERT INTO training_tasks "
            "(id, code, name, description, status, mode, progress, created_by_id, "
            "version, created_at, updated_at) VALUES "
            "('task-id', 'task-code', 'Task', '', 'draft', 'single_model', 0, "
            "'pending-id', 1, '2026-09-20', '2026-09-20')"
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = make_engine(database_path)
    user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
    assert "must_change_password" in user_columns
    assert {"reviewed_at", "reviewed_by_id"}.isdisjoint(user_columns)
    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "SELECT status FROM users WHERE id='pending-id'"
        ).scalar_one() == "disabled"
        assert connection.exec_driver_sql(
            "SELECT status FROM users WHERE id='rejected-id'"
        ).scalar_one() == "disabled"
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM model_project_memberships"
        ).scalar_one() == 0
        assert connection.exec_driver_sql(
            "SELECT count(*) FROM model_projects WHERE training_task_id='task-id'"
        ).scalar_one() == 1

    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.exec_driver_sql(
            "INSERT INTO users "
            "(id, username, username_normalized, password_hash, status, is_system_admin, "
            "must_change_password, created_at, updated_at) VALUES "
            "('admin-2', 'admin2', 'admin2', 'hash', 'active', 1, 0, '2026-09-20', '2026-09-20')"
        )
    with engine.begin() as connection, pytest.raises(IntegrityError):
        connection.exec_driver_sql(
            "INSERT INTO users "
            "(id, username, username_normalized, password_hash, status, is_system_admin, "
            "must_change_password, created_at, updated_at) VALUES "
            "('pending-2', 'pending2', 'pending2', 'hash', 'pending', 0, 0, '2026-09-20', '2026-09-20')"
        )
    engine.dispose()


def test_short_code_migration_backfills_per_project_and_keeps_video_limit_trigger(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "workbench.sqlite3"
    monkeypatch.setenv(
        "VDW_DATABASE_URL",
        database_url(database_path).render_as_string(hide_password=False),
    )
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "0011_annotation_order")
    engine = make_engine(database_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO users "
            "(id, username, username_normalized, password_hash, status, "
            "is_system_admin, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                "owner-id",
                "owner",
                "owner",
                "hash",
                "active",
                False,
                "2026-07-28 00:00:00",
                "2026-07-28 00:00:00",
            ),
        )
        connection.exec_driver_sql(
            "INSERT INTO projects "
            "(id, name, description, creator_id, version, created_at, updated_at) "
            "VALUES (?, ?, '', 'owner-id', 1, ?, ?)",
            [
                (
                    "project-1",
                    "one",
                    "2026-07-28 00:00:00",
                    "2026-07-28 00:00:00",
                ),
                (
                    "project-2",
                    "two",
                    "2026-07-28 00:00:00",
                    "2026-07-28 00:00:00",
                ),
            ],
        )
        connection.exec_driver_sql(
            "INSERT INTO videos "
            "(id, project_id, source_type, title, status, enabled, version, "
            "created_at, updated_at) "
            "VALUES (?, ?, 'local', ?, 'ready', 1, 1, ?, ?)",
            [
                (
                    "video-b",
                    "project-1",
                    "second",
                    "2026-07-28 00:00:02",
                    "2026-07-28 00:00:02",
                ),
                (
                    "video-a",
                    "project-1",
                    "first",
                    "2026-07-28 00:00:01",
                    "2026-07-28 00:00:01",
                ),
                (
                    "video-c",
                    "project-2",
                    "other",
                    "2026-07-28 00:00:01",
                    "2026-07-28 00:00:01",
                ),
            ],
        )
    engine.dispose()

    command.upgrade(config, "head")
    engine = make_engine(database_path)
    with engine.connect() as connection:
        rows = connection.exec_driver_sql(
            "SELECT project_id, short_code FROM videos "
            "ORDER BY project_id, short_code"
        ).all()
        trigger = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master "
            "WHERE type='trigger' AND name='trg_videos_project_limit'"
        ).scalar_one()

    assert rows == [
        ("project-1", "00000001"),
        ("project-1", "00000002"),
        ("project-2", "00000001"),
    ]
    assert trigger == "trg_videos_project_limit"
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


def test_labels_are_unique_per_project_and_follow_project_lifecycle(tmp_path):
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
        session.add_all(
            [
                Project(id="project-1", name="one", creator_id="owner-id"),
                Project(id="project-2", name="two", creator_id="owner-id"),
            ]
        )
        session.flush()
        session.add_all(
            [
                ProjectLabel(
                    id="label-1",
                    project_id="project-1",
                    name="helmet",
                    name_normalized="helmet",
                    color="#16866f",
                    sort_order=0,
                ),
                ProjectLabel(
                    id="label-2",
                    project_id="project-2",
                    name="helmet",
                    name_normalized="helmet",
                    color="#17212b",
                    sort_order=0,
                ),
            ]
        )
        session.commit()

    with Session(engine) as session:
        session.add(
            ProjectLabel(
                project_id="project-1",
                name="Helmet",
                name_normalized="helmet",
                color="#78d2b8",
                sort_order=1,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()

    with Session(engine) as session:
        project = session.get(Project, "project-1")
        assert project is not None
        session.delete(project)
        session.commit()
        assert session.scalars(
            select(ProjectLabel).where(ProjectLabel.project_id == "project-1")
        ).all() == []
        assert session.get(ProjectLabel, "label-2") is not None
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


def test_project_video_limit_and_enabled_default_are_enforced(tmp_path):
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
        session.add_all(
            [
                Project(id="project-1", name="one", creator_id="owner-id"),
                Project(id="project-2", name="two", creator_id="owner-id"),
            ]
        )
        session.commit()

        session.add_all(
            [
                Video(
                    id=f"video-{index}",
                    project_id="project-1",
                    source_type="local",
                    title=f"video {index}",
                )
                for index in range(999)
            ]
        )
        session.commit()
        first = session.get(Video, "video-0")
        assert first is not None
        assert first.enabled is True

        session.add(
            Video(
                id="video-1000",
                project_id="project-1",
                source_type="local",
                title="too many",
            )
        )
        with pytest.raises(IntegrityError, match="project video limit reached"):
            session.commit()
        session.rollback()

        session.add(
            Video(
                id="other-project-video",
                project_id="project-2",
                source_type="local",
                title="other project",
            )
        )
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


def test_label_description_migration_backfills_existing_labels(tmp_path, monkeypatch):
    database_path = tmp_path / "db" / "workbench.sqlite3"
    database_path.parent.mkdir(parents=True)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    monkeypatch.setenv(
        "VDW_DATABASE_URL", database_url(database_path).render_as_string(hide_password=False)
    )
    command.upgrade(config, "0007_labels")
    engine = make_engine(database_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO users
                (id, username, username_normalized, password_hash, status,
                 is_system_admin, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "owner-id",
                "owner",
                "owner",
                "hash",
                "active",
                False,
                "2026-07-27 00:00:00.000000",
                "2026-07-27 00:00:00.000000",
            ),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO projects
                (id, name, description, creator_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "project-id",
                "project",
                "",
                "owner-id",
                "2026-07-27 00:00:00.000000",
                "2026-07-27 00:00:00.000000",
            ),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO labels
                (id, project_id, name, name_normalized, color, sort_order,
                 enabled, version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "label-id",
                "project-id",
                "helmet",
                "helmet",
                "#16866f",
                0,
                True,
                1,
                "2026-07-27 00:00:00.000000",
                "2026-07-27 00:00:00.000000",
            ),
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = make_engine(database_path)
    with Session(engine) as session:
        label = session.get(ProjectLabel, "label-id")
    assert label is not None
    assert label.description_zh == ""
    engine.dispose()


def test_annotation_migration_backfills_frames_and_cascades(tmp_path, monkeypatch):
    database_path = tmp_path / "db" / "workbench.sqlite3"
    database_path.parent.mkdir(parents=True)
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    monkeypatch.setenv(
        "VDW_DATABASE_URL", database_url(database_path).render_as_string(hide_password=False)
    )
    command.upgrade(config, "0008_label_description_zh")
    engine = make_engine(database_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            """
            INSERT INTO users
                (id, username, username_normalized, password_hash, status,
                 is_system_admin, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "owner-id", "owner", "owner", "hash", "active", False,
                "2026-07-27 00:00:00.000000", "2026-07-27 00:00:00.000000",
            ),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO projects
                (id, name, description, creator_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                "project-id", "project", "", "owner-id",
                "2026-07-27 00:00:00.000000", "2026-07-27 00:00:00.000000",
            ),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO videos
                (id, project_id, source_type, title, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "video-id", "project-id", "local", "video", "ready",
                "2026-07-27 00:00:00.000000", "2026-07-27 00:00:00.000000",
            ),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO frames
                (id, video_id, generation, sequence, source_frame_index,
                 time_offset, file_path, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "frame-id", "video-id", 1, 1, 0, 0,
                "projects/project-id/frames/video-id/000001.jpg", True,
                "2026-07-27 00:00:00.000000",
            ),
        )
        connection.exec_driver_sql(
            """
            INSERT INTO labels
                (id, project_id, name, name_normalized, description_zh, color,
                 sort_order, enabled, version, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "label-id", "project-id", "helmet", "helmet", "安全帽",
                "#16866f", 0, True, 1,
                "2026-07-27 00:00:00.000000", "2026-07-27 00:00:00.000000",
            ),
        )
    engine.dispose()
    command.upgrade(config, "0010_inference_models")

    engine = make_engine(database_path)
    with engine.begin() as connection:
        for annotation_id in ("annotation-b", "annotation-a"):
            connection.exec_driver_sql(
                """
                INSERT INTO annotations
                    (id, frame_id, label_id, x_min, y_min, x_max, y_max,
                     source, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    annotation_id, "frame-id", "label-id", 10, 20, 110, 220,
                    "manual", None, "2026-07-27 00:00:00.000000",
                ),
            )
    engine.dispose()
    command.upgrade(config, "head")

    engine = make_engine(database_path)
    with Session(engine) as session:
        frame = session.get(Frame, "frame-id")
        assert frame is not None
        assert frame.annotation_revision == 1
        legacy = session.query(FrameAnnotation).order_by(FrameAnnotation.sort_order).all()
        assert [(item.id, item.sort_order) for item in legacy] == [
            ("annotation-a", 0),
            ("annotation-b", 1),
        ]
        session.add(
            FrameAnnotation(
                id="annotation-id",
                frame_id="frame-id",
                label_id="label-id",
                x_min=10,
                y_min=20,
                x_max=110,
                y_max=220,
                source="manual",
            )
        )
        session.commit()
        session.delete(frame)
        session.commit()
        assert session.get(FrameAnnotation, "annotation-id") is None

    with Session(engine) as session:
        session.add(
            FrameAnnotation(
                id="invalid-annotation",
                frame_id="missing-frame",
                label_id="label-id",
                x_min=20,
                y_min=20,
                x_max=10,
                y_max=30,
                source="unknown",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()


def test_inference_models_and_auto_annotation_task_constraints(tmp_path):
    database_path = tmp_path / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    with Session(engine) as session:
        official = session.scalar(
            select(ModelProject).where(
                ModelProject.system_key == OFFICIAL_YOLO11_SYSTEM_KEY
            )
        )
        assert official is not None
        session.add(
            User(
                id="admin-id",
                username="admin",
                username_normalized="admin",
                password_hash="hash",
                is_system_admin=True,
            )
        )
        session.flush()
        session.add(Project(id="project-id", name="project", creator_id="admin-id"))
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
            InferenceModel(
                id="model-id",
                model_project_id=OFFICIAL_YOLO11_MODEL_PROJECT_ID,
                name="YOLO detector",
                kind="yolo",
                status="ready",
                storage_path="models/model-id/model.pt",
                source_name="model.pt",
                created_by_id="admin-id",
            )
        )
        session.add_all(
            [
                Task(
                    id="import-model-task",
                    project_id=None,
                    model_project_id=OFFICIAL_YOLO11_MODEL_PROJECT_ID,
                    submitted_by_id="admin-id",
                    type="import_model",
                ),
                Task(
                    id="auto-task",
                    project_id="project-id",
                    submitted_by_id="admin-id",
                    video_id="video-id",
                    type="auto_annotate",
                ),
            ]
        )
        session.commit()

        session.add(
            InferenceModel(
                model_project_id=OFFICIAL_YOLO11_MODEL_PROJECT_ID,
                name="invalid",
                kind="unknown",
                status="ready",
                source_name="invalid.bin",
                created_by_id="admin-id",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
        session.add(
            User(
                id="remote-user-id",
                username="remote",
                username_normalized="remote",
                password_hash="hash",
            )
        )
        session.flush()
        session.add(
            UserXAnyLabelingSetting(
                user_id="remote-user-id",
                server_url="http://127.0.0.1:44444",
            )
        )
        session.commit()
        session.delete(session.get(User, "remote-user-id"))
        session.commit()
        assert session.get(UserXAnyLabelingSetting, "remote-user-id") is None
    engine.dispose()


def _upgrade_to_access_control(database_path, monkeypatch) -> Config:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(
        "VDW_DATABASE_URL",
        database_url(database_path).render_as_string(hide_password=False),
    )
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "0026_access_control_refactor")
    return config


def test_official_model_project_migration_converts_existing_project_and_cleans_files(
    tmp_path, monkeypatch
):
    workspace = tmp_path / ".vision-dataset-workbench"
    database_path = workspace / "db" / "workbench.sqlite3"
    _upgrade_to_access_control(database_path, monkeypatch)
    engine = make_engine(database_path)
    existing_id = "000001aa-0000-4000-8000-000000000001"
    temporary_model_id = "10000000-0000-4000-8000-000000000001"
    official_model_id = "10000000-0000-4000-8000-000000000002"
    with Session(engine) as session:
        owner = User(
            id="owner-id",
            username="owner",
            username_normalized="owner",
            password_hash="hash",
        )
        member = User(
            id="member-id",
            username="member",
            username_normalized="member",
            password_hash="hash",
        )
        session.add_all((owner, member))
        session.flush()
        session.add(
            ModelProject(
                id=existing_id,
                name=OFFICIAL_YOLO11_MODEL_PROJECT_NAME,
                name_normalized=OFFICIAL_YOLO11_MODEL_PROJECT_NAME.lower(),
                description="existing models",
                series_type="archive",
                created_by_id=owner.id,
            )
        )
        session.flush()
        session.add(
            ModelProjectMembership(
                model_project_id=existing_id,
                user_id=member.id,
                role="editor",
            )
        )
        session.add_all(
            (
                InferenceModel(
                    id=temporary_model_id,
                    model_project_id="00000000-0000-0000-0000-000000000001",
                    name="temporary",
                    kind="yolo",
                    status="ready",
                    source_name="temporary.pt",
                    created_by_id=owner.id,
                ),
                InferenceModel(
                    id=official_model_id,
                    model_project_id=existing_id,
                    name="official",
                    kind="yolo",
                    status="ready",
                    source_name="official.pt",
                    created_by_id=owner.id,
                ),
            )
        )
        session.commit()
    engine.dispose()
    temporary_model_dir = workspace / "models" / temporary_model_id
    temporary_project_dir = (
        workspace / "model-projects" / "00000000-0000-0000-0000-000000000001"
    )
    temporary_model_dir.mkdir(parents=True)
    temporary_project_dir.mkdir(parents=True)

    create_workspace_database(database_path)

    engine = make_engine(database_path)
    with Session(engine) as session:
        official = session.get(ModelProject, existing_id)
        assert official is not None
        assert official.system_key == OFFICIAL_YOLO11_SYSTEM_KEY
        assert official.created_by_id is None
        assert session.get(InferenceModel, official_model_id) is not None
        assert session.get(InferenceModel, temporary_model_id) is None
        assert session.query(ModelProjectMembership).filter_by(
            model_project_id=existing_id
        ).count() == 0
        assert session.scalar(
            select(ModelProject).where(ModelProject.system_key == "temporary")
        ) is None
    engine.dispose()
    assert not temporary_model_dir.exists()
    assert not temporary_project_dir.exists()


def test_official_model_project_migration_preserves_existing_candidate_id(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "workbench.sqlite3"
    config = _upgrade_to_access_control(database_path, monkeypatch)
    engine = make_engine(database_path)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO model_projects "
            "(id, name, name_normalized, description, series_type, system_key, "
            "version, created_at, updated_at) VALUES (?, ?, ?, '', 'archive', NULL, 1, ?, ?)",
            (
                "99999900-0000-4000-8000-000000000001",
                OFFICIAL_YOLO11_MODEL_PROJECT_NAME,
                OFFICIAL_YOLO11_MODEL_PROJECT_NAME.lower(),
                "2026-09-21",
                "2026-09-21",
            ),
        )
    engine.dispose()

    command.upgrade(config, "head")

    engine = make_engine(database_path)
    with Session(engine) as session:
        official = session.get(
            ModelProject, "99999900-0000-4000-8000-000000000001"
        )
        assert official is not None
        assert official.system_key == OFFICIAL_YOLO11_SYSTEM_KEY
        assert session.get(ModelProject, OFFICIAL_YOLO11_MODEL_PROJECT_ID) is None
    engine.dispose()


def test_official_model_project_migration_rejects_external_training_reference(
    tmp_path, monkeypatch
):
    database_path = tmp_path / "workbench.sqlite3"
    config = _upgrade_to_access_control(database_path, monkeypatch)
    engine = make_engine(database_path)
    temporary_model_id = "10000000-0000-4000-8000-000000000003"
    with Session(engine) as session:
        owner = User(
            id="owner-id",
            username="owner",
            username_normalized="owner",
            password_hash="hash",
        )
        session.add(owner)
        session.flush()
        session.add(
            InferenceModel(
                id=temporary_model_id,
                model_project_id="00000000-0000-0000-0000-000000000001",
                name="temporary",
                kind="yolo",
                status="ready",
                source_name="temporary.pt",
                created_by_id=owner.id,
            )
        )
        session.flush()
        session.add(
            TrainingTask(
                code="uses-temporary",
                name="Uses temporary",
                default_base_model_id=temporary_model_id,
                created_by_id=owner.id,
            )
        )
        session.commit()
    engine.dispose()

    with pytest.raises(RuntimeError, match="training resource"):
        command.upgrade(config, "head")


def test_dataset_export_schema_and_active_project_constraint(tmp_path):
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
        task = Task(
            id="export-task",
            project_id="project-id",
            submitted_by_id="owner-id",
            type="export_dataset",
        )
        session.add(task)
        session.flush()
        session.add(
            DatasetExport(
                id="export-id",
                project_id="project-id",
                task_id=task.id,
                created_by_id="owner-id",
                name="dataset",
                status="queued",
                train_ratio=0.8,
                label_snapshot="[]",
                source_snapshot='{"videos": []}',
            )
        )
        session.commit()

        session.add(
            DatasetExport(
                id="second-export",
                project_id="project-id",
                created_by_id="owner-id",
                name="dataset-2",
                status="running",
                train_ratio=0.8,
                label_snapshot="[]",
                source_snapshot='{"videos": []}',
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
    engine.dispose()
