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
    Project,
    ProjectLabel,
    ProjectMembership,
    SamplingPlan,
    Task,
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
    }.issubset(
        inspect(engine).get_table_names()
    )
    assert {"default_dataset_mode", "default_multi_dataset_config"} <= {
        column["name"] for column in inspect(engine).get_columns("training_tasks")
    }
    assert {"dataset_mode", "multi_dataset_config"} <= {
        column["name"] for column in inspect(engine).get_columns("training_models")
    }
    assert AuthSession.__tablename__ == "sessions"
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
        temporary = session.scalar(
            select(ModelProject).where(ModelProject.system_key == "temporary")
        )
        assert temporary is not None
        assert temporary.name == "临时模型项目"
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
                    model_project_id="00000000-0000-0000-0000-000000000001",
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
