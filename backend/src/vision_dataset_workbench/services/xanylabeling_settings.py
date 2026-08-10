import json
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..config import RuntimeSettings
from ..models import Task, User, UserXAnyLabelingSetting
from ..security.credentials import CredentialCipher
from ..xanylabeling import (
    RemoteModelOption,
    XAnyLabelingClient,
    XAnyLabelingUnavailable,
    normalize_server_url,
)


class InvalidXAnyLabelingSetting(ValueError):
    pass


class XAnyLabelingSettingConflict(ValueError):
    pass


class XAnyLabelingSettingUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class PublicXAnyLabelingSetting:
    configured: bool
    server_url: str
    has_api_key: bool
    available: bool


@dataclass(frozen=True)
class XAnyLabelingConnection:
    server_url: str
    api_key: str | None


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class XAnyLabelingSettingsService:
    def __init__(
        self,
        engine: Engine,
        settings: RuntimeSettings,
        *,
        client_factory=XAnyLabelingClient,
    ):
        self.settings = settings
        self.client_factory = client_factory
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def get_public(self, actor: User) -> PublicXAnyLabelingSetting:
        with self._session_factory() as database:
            record = database.get(UserXAnyLabelingSetting, actor.id)
            return self._public(record)

    def save_verified(
        self,
        actor: User,
        server_url: str,
        api_key_mode: str,
        api_key: str | None,
    ) -> tuple[PublicXAnyLabelingSetting, list[RemoteModelOption]]:
        if api_key_mode not in {"retain", "replace", "clear"}:
            raise InvalidXAnyLabelingSetting("API key mode is invalid")
        try:
            normalized_url = normalize_server_url(server_url)
        except XAnyLabelingUnavailable as exc:
            raise InvalidXAnyLabelingSetting(str(exc)) from exc
        with self._session_factory() as database:
            if self._has_active_remote_task(database, actor.id):
                raise XAnyLabelingSettingConflict(
                    "X-AnyLabeling settings cannot change during an active task"
                )
            existing = database.get(UserXAnyLabelingSetting, actor.id)
            resolved_key = self._resolve_api_key(existing, api_key_mode, api_key)
        try:
            models = self.client_factory(normalized_url, resolved_key).list_models()
        except XAnyLabelingUnavailable as exc:
            raise XAnyLabelingSettingUnavailable(str(exc)) from exc

        encrypted = (
            CredentialCipher(self.settings.credential_encryption_key).encrypt(resolved_key)
            if resolved_key is not None
            else None
        )
        now = _utc_now()
        with self._session_factory() as database:
            record = database.get(UserXAnyLabelingSetting, actor.id)
            if record is None:
                record = UserXAnyLabelingSetting(
                    user_id=actor.id,
                    server_url=normalized_url,
                    api_key_ciphertext=encrypted,
                    created_at=now,
                    updated_at=now,
                )
                database.add(record)
            else:
                record.server_url = normalized_url
                record.api_key_ciphertext = encrypted
                record.updated_at = now
            database.commit()
            return self._public(record), models

    def list_models(self, actor: User) -> list[RemoteModelOption]:
        connection = self.connection_for(actor.id)
        try:
            return self.client_factory(
                connection.server_url, connection.api_key
            ).list_models()
        except XAnyLabelingUnavailable as exc:
            raise XAnyLabelingSettingUnavailable(str(exc)) from exc

    def connection_for(self, user_id: str) -> XAnyLabelingConnection:
        with self._session_factory() as database:
            record = database.get(UserXAnyLabelingSetting, user_id)
            if record is None:
                raise InvalidXAnyLabelingSetting(
                    "X-AnyLabeling server is not configured"
                )
            api_key = (
                CredentialCipher(self.settings.credential_encryption_key).decrypt(
                    record.api_key_ciphertext
                )
                if record.api_key_ciphertext
                else None
            )
            return XAnyLabelingConnection(record.server_url, api_key)

    def client_for(self, user_id: str) -> XAnyLabelingClient:
        connection = self.connection_for(user_id)
        return self.client_factory(connection.server_url, connection.api_key)

    @staticmethod
    def _public(
        record: UserXAnyLabelingSetting | None,
    ) -> PublicXAnyLabelingSetting:
        return PublicXAnyLabelingSetting(
            configured=record is not None,
            server_url=record.server_url if record else "",
            has_api_key=bool(record and record.api_key_ciphertext),
            available=record is not None,
        )

    def _resolve_api_key(
        self,
        existing: UserXAnyLabelingSetting | None,
        mode: str,
        candidate: str | None,
    ) -> str | None:
        if mode == "clear":
            return None
        if mode == "replace":
            if candidate is None or not candidate:
                raise InvalidXAnyLabelingSetting("API key is required when replacing")
            return candidate
        if existing is None or not existing.api_key_ciphertext:
            return None
        return CredentialCipher(self.settings.credential_encryption_key).decrypt(
            existing.api_key_ciphertext
        )

    @staticmethod
    def _has_active_remote_task(database, user_id: str) -> bool:
        payloads = database.scalars(
            select(Task.payload).where(
                Task.submitted_by_id == user_id,
                Task.type == "auto_annotate",
                Task.status.in_(("queued", "running")),
            )
        )
        # ponytail: active task counts are small; add a JSON index only if this scan is measured.
        return any(json.loads(payload).get("source") == "xanylabeling" for payload in payloads)
