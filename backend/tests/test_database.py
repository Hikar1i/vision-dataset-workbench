from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from vision_dataset_workbench.database import (
    create_workspace_database,
    make_engine,
    sqlite_supports_safe_wal,
)
from vision_dataset_workbench.models import User
from vision_dataset_workbench.security.passwords import hash_password, verify_password


def test_migration_creates_users_and_password_hash_round_trips(tmp_path):
    database_path = tmp_path / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)

    assert "users" in inspect(engine).get_table_names()
    with engine.connect() as connection:
        journal_mode = connection.exec_driver_sql("PRAGMA journal_mode").scalar_one()
    assert journal_mode == ("wal" if sqlite_supports_safe_wal() else "delete")
    password_hash = hash_password("correct horse battery staple")
    with Session(engine) as session:
        session.add(User(username="admin", password_hash=password_hash, is_system_admin=True))
        session.commit()
        user = session.scalar(select(User).where(User.username == "admin"))

    assert user is not None
    assert verify_password(user.password_hash, "correct horse battery staple")
    engine.dispose()
