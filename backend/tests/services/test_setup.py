import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vision_dataset_workbench.database import make_engine
from vision_dataset_workbench.models import User
from vision_dataset_workbench.services.setup import SetupConflict, SetupService
from vision_dataset_workbench.setup.tokens import SetupToken
from vision_dataset_workbench.storage.locator import WorkspaceLocator


def test_setup_creates_workspace_and_admin(tmp_path):
    home = tmp_path / "home"
    parent = home / "data"
    parent.mkdir(parents=True)
    token = SetupToken.create()
    locator = WorkspaceLocator(tmp_path / "config" / "instance.json")
    service = SetupService(home, locator, token)

    workspace = service.initialize(
        token=token.plaintext,
        parent_relative="data",
        username="admin",
        password="correct horse battery staple",
    )

    assert workspace == parent / ".vision-dataset-workbench"
    assert locator.read() == workspace.resolve()
    with Session(make_engine(workspace / "db" / "workbench.sqlite3")) as session:
        admin = session.scalar(select(User).where(User.username == "admin"))
    assert admin is not None and admin.is_system_admin
    assert admin.username_normalized == "admin"


def test_setup_refuses_existing_workspace(tmp_path):
    home = tmp_path / "home"
    parent = home / "data"
    (parent / ".vision-dataset-workbench").mkdir(parents=True)
    token = SetupToken.create()
    service = SetupService(home, WorkspaceLocator(tmp_path / "locator.json"), token)

    with pytest.raises(SetupConflict):
        service.initialize(token.plaintext, "data", "admin", "a secure password")


def test_setup_rolls_back_when_locator_write_fails(tmp_path, monkeypatch):
    home = tmp_path / "home"
    parent = home / "data"
    parent.mkdir(parents=True)
    token = SetupToken.create()
    locator = WorkspaceLocator(tmp_path / "config" / "instance.json")
    service = SetupService(home, locator, token)

    def fail_write(_workspace):
        raise OSError("locator unavailable")

    monkeypatch.setattr(locator, "write", fail_write)

    with pytest.raises(OSError, match="locator unavailable"):
        service.initialize(token.plaintext, "data", "admin", "a secure password")

    assert not (parent / ".vision-dataset-workbench").exists()
    assert not list(parent.glob(".vision-dataset-workbench-initializing-*"))
    token.verify(token.plaintext)
