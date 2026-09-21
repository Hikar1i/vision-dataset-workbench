import os
import shutil
import sqlite3
from pathlib import Path
from uuid import UUID

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, event
from sqlalchemy.engine import URL


def database_url(path: Path) -> URL:
    return URL.create("sqlite", database=str(path.resolve()))


def sqlite_supports_safe_wal() -> bool:
    version = sqlite3.sqlite_version_info
    return version >= (3, 51, 3) or version in {(3, 44, 6), (3, 50, 7)}


def make_engine(path: Path) -> Engine:
    engine = create_engine(database_url(path), connect_args={"timeout": 5})

    @event.listens_for(engine, "connect")
    def configure_sqlite(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute(
            "PRAGMA journal_mode=WAL" if sqlite_supports_safe_wal() else "PRAGMA journal_mode=DELETE"
        )
        cursor.close()

    return engine


def _temporary_model_directories(path: Path) -> tuple[Path, ...]:
    if path.name != "workbench.sqlite3" or path.parent.name != "db" or not path.is_file():
        return ()
    with sqlite3.connect(path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not {"model_projects", "inference_models"} <= tables:
            return ()
        project = connection.execute(
            "SELECT id FROM model_projects WHERE system_key='temporary'"
        ).fetchone()
        if project is None:
            return ()
        project_id = str(project[0])
        model_ids = [
            str(row[0])
            for row in connection.execute(
                "SELECT id FROM inference_models WHERE model_project_id=?",
                (project_id,),
            )
        ]

    identifiers = [project_id, *model_ids]
    if any(str(UUID(identifier)) != identifier.lower() for identifier in identifiers):
        raise RuntimeError("temporary model project contains an invalid managed directory id")
    workspace = path.parent.parent.resolve()
    directories = [
        workspace / "models" / model_id for model_id in model_ids
    ] + [workspace / "model-projects" / project_id]
    for directory in directories:
        if directory.is_symlink():
            raise RuntimeError(f"refusing to delete symlinked managed directory: {directory}")
        if directory.exists() and not directory.is_dir():
            raise RuntimeError(f"managed model path is not a directory: {directory}")
        if not directory.resolve().is_relative_to(workspace):
            raise RuntimeError(f"managed model path escapes the workspace: {directory}")
    return tuple(directories)


def create_workspace_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_directories = _temporary_model_directories(path)
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    previous = os.environ.get("VDW_DATABASE_URL")
    # ponytail: setup is single-process; use Alembic config attributes if migrations become concurrent.
    os.environ["VDW_DATABASE_URL"] = database_url(path).render_as_string(hide_password=False)
    try:
        command.upgrade(config, "head")
    finally:
        if previous is None:
            os.environ.pop("VDW_DATABASE_URL", None)
        else:
            os.environ["VDW_DATABASE_URL"] = previous
    for directory in temporary_directories:
        if directory.exists():
            shutil.rmtree(directory)
