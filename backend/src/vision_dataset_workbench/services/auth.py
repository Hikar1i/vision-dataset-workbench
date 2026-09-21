import hashlib
import re
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from ..config import RuntimeSettings
from ..database import create_workspace_database, make_engine
from ..models import AuthSession, User
from ..security.passwords import hash_password, verify_password

COOKIE_NAME = "vdw_session"
IDLE_LIFETIME = timedelta(hours=12)
ABSOLUTE_LIFETIME = timedelta(days=7)
TOUCH_INTERVAL = timedelta(minutes=5)
MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 256

_USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{3,64}$")
_DUMMY_PASSWORD_HASH = hash_password("invalid-login-timing-placeholder")


class AuthenticationFailed(ValueError):
    pass


class CurrentPasswordRequired(ValueError):
    pass


class AuthConflict(ValueError):
    pass


class UserNotFound(ValueError):
    pass


@dataclass(frozen=True)
class CreatedSession:
    token: str
    user: User


@dataclass(frozen=True)
class ProvisionedUser:
    user: User
    initial_password: str


def normalize_username(username: str) -> str:
    candidate = username.strip()
    if not _USERNAME_PATTERN.fullmatch(candidate):
        raise ValueError(
            "username must be 3-64 characters using letters, numbers, '.', '_' or '-'"
        )
    return candidate.lower()


def validate_password(password: str) -> None:
    if not MINIMUM_PASSWORD_LENGTH <= len(password) <= MAXIMUM_PASSWORD_LENGTH:
        raise ValueError("password must be 12-256 characters")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class AuthService:
    def __init__(
        self,
        engine: Engine,
        settings: RuntimeSettings,
        *,
        now: Callable[[], datetime] = _utc_now,
    ):
        self.settings = settings
        self._now = now
        self.engine = engine
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def login(self, username: str, password: str) -> CreatedSession:
        try:
            normalized = normalize_username(username)
        except ValueError:
            verify_password(_DUMMY_PASSWORD_HASH, password)
            raise AuthenticationFailed("invalid username or password") from None

        with self._session_factory() as database:
            user = database.scalar(
                select(User).where(User.username_normalized == normalized)
            )
            password_matches = verify_password(
                user.password_hash if user else _DUMMY_PASSWORD_HASH, password
            )
            allowed = (
                user is not None
                and password_matches
                and user.status == "active"
                and (self.settings.app_mode == "multi" or user.is_system_admin)
            )
            if not allowed:
                raise AuthenticationFailed("invalid username or password")

            created = self._create_session(database, user, self._now())
            database.commit()
            return created

    def close(self) -> None:
        self.engine.dispose()

    def authenticate(self, token: str) -> User:
        if not token:
            raise AuthenticationFailed("authentication required")

        now = self._now()
        with self._session_factory() as database:
            row = database.execute(
                select(AuthSession, User)
                .join(User, User.id == AuthSession.user_id)
                .where(AuthSession.token_hash == _token_hash(token))
            ).one_or_none()
            if row is None:
                raise AuthenticationFailed("authentication required")

            auth_session, user = row
            valid = (
                user.status == "active"
                and (self.settings.app_mode == "multi" or user.is_system_admin)
                and now < auth_session.idle_expires_at
                and now < auth_session.absolute_expires_at
            )
            if not valid:
                database.delete(auth_session)
                database.commit()
                raise AuthenticationFailed("authentication required")

            if now - auth_session.last_seen_at >= TOUCH_INTERVAL:
                auth_session.last_seen_at = now
                auth_session.idle_expires_at = min(
                    now + IDLE_LIFETIME, auth_session.absolute_expires_at
                )
                database.commit()
            return user

    def logout(self, token: str) -> None:
        if not token:
            return
        with self._session_factory() as database:
            database.execute(
                delete(AuthSession).where(AuthSession.token_hash == _token_hash(token))
            )
            database.commit()

    def change_password(
        self, token: str, current_password: str | None, new_password: str
    ) -> CreatedSession:
        authenticated_user = self.authenticate(token)
        validate_password(new_password)
        now = self._now()

        with self._session_factory() as database:
            user = database.get(User, authenticated_user.id)
            if user is None:
                raise AuthenticationFailed("authentication required")
            if not user.must_change_password and current_password is None:
                raise CurrentPasswordRequired("current password is required")
            if (
                not user.must_change_password
                and not verify_password(user.password_hash, current_password or "")
            ):
                raise AuthenticationFailed("current password is incorrect")

            user.password_hash = hash_password(new_password)
            user.must_change_password = False
            user.updated_at = now
            database.execute(
                delete(AuthSession).where(AuthSession.user_id == user.id)
            )
            replacement = self._create_session(database, user, now)
            database.commit()
            return replacement

    def revoke_user_sessions(self, user_id: str) -> None:
        with self._session_factory() as database:
            database.execute(
                delete(AuthSession).where(AuthSession.user_id == user_id)
            )
            database.commit()

    def revoke_incompatible_sessions(self) -> None:
        if self.settings.app_mode != "single":
            return
        non_admin_ids = select(User.id).where(User.is_system_admin.is_(False))
        with self._session_factory() as database:
            database.execute(
                delete(AuthSession).where(AuthSession.user_id.in_(non_admin_ids))
            )
            database.commit()

    def create_user(self, username: str) -> ProvisionedUser:
        normalized = normalize_username(username)
        initial_password = secrets.token_urlsafe(18)
        now = self._now()
        user = User(
            username=username.strip(),
            username_normalized=normalized,
            password_hash=hash_password(initial_password),
            status="active",
            is_system_admin=False,
            must_change_password=True,
            created_at=now,
            updated_at=now,
        )
        with self._session_factory() as database:
            try:
                database.add(user)
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                raise AuthConflict("username already exists") from exc
        return ProvisionedUser(user=user, initial_password=initial_password)

    def list_users(
        self, *, status: str | None, page: int, page_size: int
    ) -> tuple[list[User], int]:
        condition = User.status == status if status else None
        with self._session_factory() as database:
            total_query = select(func.count()).select_from(User)
            users_query = select(User)
            if condition is not None:
                total_query = total_query.where(condition)
                users_query = users_query.where(condition)
            total = database.scalar(total_query) or 0
            users = list(
                database.scalars(
                    users_query
                    .order_by(User.username_normalized)
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            return users, total

    def set_user_status(self, user_id: str, action: str) -> User:
        transitions = {
            "disable": ({"active"}, "disabled"),
            "enable": ({"disabled"}, "active"),
        }
        accepted_statuses, next_status = transitions[action]
        now = self._now()
        with self._session_factory() as database:
            user = database.get(User, user_id)
            if user is None:
                raise UserNotFound("user not found")
            if user.is_system_admin:
                raise AuthConflict("administrator account cannot be managed")
            if user.status not in accepted_statuses:
                raise AuthConflict("user status does not allow this action")

            user.status = next_status
            user.updated_at = now
            if next_status != "active":
                database.execute(
                    delete(AuthSession).where(AuthSession.user_id == user.id)
                )
            database.commit()
            return user

    def reset_user_password(self, user_id: str) -> ProvisionedUser:
        initial_password = secrets.token_urlsafe(18)
        now = self._now()
        with self._session_factory() as database:
            user = database.get(User, user_id)
            if user is None:
                raise UserNotFound("user not found")
            if user.is_system_admin:
                raise AuthConflict("administrator password must be reset from the terminal")
            user.password_hash = hash_password(initial_password)
            user.must_change_password = True
            user.updated_at = now
            database.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
            database.commit()
            return ProvisionedUser(user=user, initial_password=initial_password)

    def reset_admin_password(self, username: str, new_password: str) -> User:
        try:
            normalized = normalize_username(username)
        except ValueError:
            raise UserNotFound("administrator not found") from None
        validate_password(new_password)
        replacement_hash = hash_password(new_password)
        now = self._now()
        with self._session_factory() as database:
            user = database.scalar(
                select(User).where(User.username_normalized == normalized)
            )
            if user is None or not user.is_system_admin:
                raise UserNotFound("administrator not found")
            user.password_hash = replacement_hash
            user.must_change_password = False
            user.updated_at = now
            database.execute(
                delete(AuthSession).where(AuthSession.user_id == user.id)
            )
            database.commit()
            return user

    @staticmethod
    def _create_session(
        database: Session, user: User, now: datetime
    ) -> CreatedSession:
        token = secrets.token_urlsafe(32)
        absolute_expires_at = now + ABSOLUTE_LIFETIME
        database.add(
            AuthSession(
                user_id=user.id,
                token_hash=_token_hash(token),
                created_at=now,
                last_seen_at=now,
                idle_expires_at=min(now + IDLE_LIFETIME, absolute_expires_at),
                absolute_expires_at=absolute_expires_at,
            )
        )
        return CreatedSession(token=token, user=user)


def build_auth_service(workspace: Path, settings: RuntimeSettings) -> AuthService:
    database_path = workspace / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    service = AuthService(make_engine(database_path), settings)
    service.revoke_incompatible_sessions()
    return service
