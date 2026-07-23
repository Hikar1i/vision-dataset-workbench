from datetime import datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.models import AuthSession, User
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.services.auth import AuthenticationFailed, AuthService

PASSWORD = "correct horse battery staple"
NEW_PASSWORD = "new correct horse battery"


class Clock:
    def __init__(self):
        self.value = datetime(2026, 7, 23, 0, 0, 0)

    def __call__(self):
        return self.value

    def advance(self, delta: timedelta):
        self.value += delta


@pytest.fixture
def auth_runtime(tmp_path):
    database_path = tmp_path / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    with Session(engine) as session:
        session.add_all(
            [
                User(
                    id="admin-id",
                    username="Admin",
                    username_normalized="admin",
                    password_hash=hash_password(PASSWORD),
                    status="active",
                    is_system_admin=True,
                ),
                User(
                    id="user-id",
                    username="colleague",
                    username_normalized="colleague",
                    password_hash=hash_password(PASSWORD),
                    status="active",
                    is_system_admin=False,
                ),
            ]
        )
        session.commit()
    clock = Clock()
    yield engine, clock, tmp_path
    engine.dispose()


def make_service(auth_runtime, mode="multi"):
    engine, clock, home = auth_runtime
    settings = RuntimeSettings(home=home, workspace=home, app_mode=mode)
    return AuthService(engine, settings, now=clock)


def test_login_authenticate_and_logout(auth_runtime):
    service = make_service(auth_runtime)

    created = service.login("ADMIN", PASSWORD)

    assert created.user.id == "admin-id"
    assert service.authenticate(created.token).id == "admin-id"
    service.logout(created.token)
    with pytest.raises(AuthenticationFailed):
        service.authenticate(created.token)


def test_login_rejects_wrong_password_and_single_mode_non_admin(auth_runtime):
    multi = make_service(auth_runtime)
    with pytest.raises(AuthenticationFailed):
        multi.login("missing", PASSWORD)
    with pytest.raises(AuthenticationFailed):
        multi.login("admin", "wrong password")

    single = make_service(auth_runtime, mode="single")
    assert single.login("admin", PASSWORD).user.is_system_admin
    with pytest.raises(AuthenticationFailed):
        single.login("colleague", PASSWORD)


def test_authentication_throttles_touch_and_enforces_idle_expiry(auth_runtime):
    service = make_service(auth_runtime)
    _, clock, _ = auth_runtime
    created = service.login("admin", PASSWORD)

    clock.advance(timedelta(minutes=4))
    service.authenticate(created.token)
    with Session(auth_runtime[0]) as session:
        stored = session.scalar(select(AuthSession))
        assert stored is not None
        assert stored.last_seen_at == datetime(2026, 7, 23, 0, 0, 0)

    clock.advance(timedelta(minutes=2))
    service.authenticate(created.token)
    with Session(auth_runtime[0]) as session:
        stored = session.scalar(select(AuthSession))
        assert stored is not None
        assert stored.last_seen_at == clock.value

    clock.advance(timedelta(hours=12, seconds=1))
    with pytest.raises(AuthenticationFailed):
        service.authenticate(created.token)


def test_authentication_enforces_absolute_expiry(auth_runtime):
    service = make_service(auth_runtime)
    _, clock, _ = auth_runtime
    created = service.login("admin", PASSWORD)

    for _ in range(15):
        clock.advance(timedelta(hours=11))
        service.authenticate(created.token)
    clock.advance(timedelta(hours=3, seconds=1))

    with pytest.raises(AuthenticationFailed):
        service.authenticate(created.token)


def test_password_change_revokes_old_sessions(auth_runtime):
    service = make_service(auth_runtime)
    first = service.login("admin", PASSWORD)
    second = service.login("admin", PASSWORD)

    replacement = service.change_password(first.token, PASSWORD, NEW_PASSWORD)

    for token in (first.token, second.token):
        with pytest.raises(AuthenticationFailed):
            service.authenticate(token)
    assert service.authenticate(replacement.token).id == "admin-id"
    with pytest.raises(AuthenticationFailed):
        service.login("admin", PASSWORD)
    assert service.login("admin", NEW_PASSWORD).user.id == "admin-id"


def test_single_mode_startup_revokes_non_admin_sessions(auth_runtime):
    multi = make_service(auth_runtime)
    admin = multi.login("admin", PASSWORD)
    colleague = multi.login("colleague", PASSWORD)

    single = make_service(auth_runtime, mode="single")
    single.revoke_incompatible_sessions()

    assert single.authenticate(admin.token).id == "admin-id"
    with pytest.raises(AuthenticationFailed):
        single.authenticate(colleague.token)
