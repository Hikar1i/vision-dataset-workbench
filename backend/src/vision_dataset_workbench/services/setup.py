import shutil
from pathlib import Path
from uuid import uuid4

from sqlalchemy.orm import Session

from ..database import create_workspace_database, make_engine
from ..models import User
from ..security.passwords import hash_password
from ..setup.tokens import SetupToken
from ..storage.locator import WorkspaceLocator
from ..storage.paths import HomePathResolver


class SetupConflict(ValueError):
    pass


class SetupService:
    SUBDIRECTORIES = ("config", "db", "projects", "models", "tasks", "tmp")

    def __init__(self, home: Path, locator: WorkspaceLocator, setup_token: SetupToken):
        self.resolver = HomePathResolver(home)
        self.locator = locator
        self.setup_token = setup_token

    def initialize(
        self, token: str, parent_relative: str, username: str, password: str
    ) -> Path:
        self.setup_token.verify(token)
        parent = self.resolver.resolve_existing(parent_relative)
        workspace = parent / ".vision-dataset-workbench"
        if workspace.exists():
            raise SetupConflict("workspace already exists")

        temporary = parent / f".vision-dataset-workbench-initializing-{uuid4()}"
        try:
            temporary.mkdir()
            for name in self.SUBDIRECTORIES:
                (temporary / name).mkdir()
            database_path = temporary / "db" / "workbench.sqlite3"
            create_workspace_database(database_path)
            engine = make_engine(database_path)
            try:
                with Session(engine) as session:
                    session.add(
                        User(
                            username=username,
                            username_normalized=username.lower(),
                            password_hash=hash_password(password),
                            status="active",
                            is_system_admin=True,
                        )
                    )
                    session.commit()
            finally:
                engine.dispose()
            temporary.replace(workspace)
            try:
                self.locator.write(workspace)
            except Exception:
                shutil.rmtree(workspace)
                raise
            self.setup_token.consume(token)
            return workspace
        except Exception:
            if temporary.exists():
                shutil.rmtree(temporary)
            raise
