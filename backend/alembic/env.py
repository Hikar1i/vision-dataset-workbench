import os

from alembic import context
from sqlalchemy import create_engine

from vision_dataset_workbench.models import Base

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(url=os.environ["VDW_DATABASE_URL"], target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(os.environ["VDW_DATABASE_URL"])
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


run_migrations_offline() if context.is_offline_mode() else run_migrations_online()
