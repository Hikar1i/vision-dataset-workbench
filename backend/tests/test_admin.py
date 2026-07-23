import pytest
from sqlalchemy.orm import Session

from vision_dataset_workbench.admin import main
from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.models import User
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.services.auth import AuthenticationFailed, AuthService

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "new correct horse battery"


@pytest.fixture
def workspace(tmp_path):
    path = tmp_path / ".vision-dataset-workbench"
    database_path = path / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    username="admin",
                    username_normalized="admin",
                    password_hash=hash_password(PASSWORD),
                    status="active",
                    is_system_admin=True,
                ),
                User(
                    username="colleague",
                    username_normalized="colleague",
                    password_hash=hash_password(PASSWORD),
                    status="active",
                    is_system_admin=False,
                ),
            ]
        )
        session.commit()
    engine.dispose()
    return path


def service_for(workspace):
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    return AuthService(
        engine, RuntimeSettings(home=workspace.parent, workspace=workspace)
    )


def test_reset_password_reads_secret_and_revokes_sessions(workspace):
    service = service_for(workspace)
    old_session = service.login("admin", PASSWORD)
    service.close()
    prompts = iter([NEW_PASSWORD, NEW_PASSWORD])

    result = main(
        ["reset-password", "--workspace", str(workspace), "--username", "ADMIN"],
        password_reader=lambda _prompt: next(prompts),
    )

    assert result == 0
    service = service_for(workspace)
    with pytest.raises(AuthenticationFailed):
        service.authenticate(old_session.token)
    with pytest.raises(AuthenticationFailed):
        service.login("admin", PASSWORD)
    assert service.login("admin", NEW_PASSWORD).user.username == "admin"
    service.close()


def test_reset_rejects_non_admin_and_mismatched_passwords(workspace, capsys):
    matching = iter([NEW_PASSWORD, NEW_PASSWORD])
    assert (
        main(
            [
                "reset-password",
                "--workspace",
                str(workspace),
                "--username",
                "colleague",
            ],
            password_reader=lambda _prompt: next(matching),
        )
        == 1
    )
    mismatched = iter([NEW_PASSWORD, f"{NEW_PASSWORD} different"])
    assert (
        main(
            ["reset-password", "--workspace", str(workspace), "--username", "admin"],
            password_reader=lambda _prompt: next(mismatched),
        )
        == 1
    )
    assert "password" in capsys.readouterr().err.lower()


def test_reset_requires_existing_workspace_and_has_no_password_argument(
    workspace, capsys
):
    assert (
        main(
            [
                "reset-password",
                "--workspace",
                str(workspace / "missing"),
                "--username",
                "admin",
            ],
            password_reader=lambda _prompt: NEW_PASSWORD,
        )
        == 1
    )
    with pytest.raises(SystemExit):
        main(
            [
                "reset-password",
                "--workspace",
                str(workspace),
                "--username",
                "admin",
                "--password",
                NEW_PASSWORD,
            ]
        )
    assert "workspace" in capsys.readouterr().err.lower()
