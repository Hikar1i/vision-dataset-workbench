import os
import sqlite3
from pathlib import Path

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


def create_workspace_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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
