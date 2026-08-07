import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..config import RuntimeSettings
from ..models import User, UserLLMConfig, UserLLMDefaults
from ..security.credentials import CredentialCipher, mask_credential
from .llm_annotation import probe

DEFAULT_OPTIONS = {
    "connection_timeout_seconds": 10,
    "inference_timeout_seconds": 120,
    "confidence": 0.25,
    "temperature": 0.2,
    "request_interval_seconds": 0,
    "retry_interval_seconds": 2,
    "max_retries": 2,
}


@dataclass(frozen=True)
class LLMConfigView:
    id: str
    name: str
    description: str
    base_url: str
    api_type: str
    model_name: str
    has_api_key: bool
    masked_api_key: str | None
    enabled: bool
    available: bool
    last_test_status: str
    last_test_latency_ms: int | None
    advanced_options: dict[str, object]
    version: int
    created_at: datetime
    updated_at: datetime


class LLMConfigService:
    def __init__(self, engine: Engine, settings: RuntimeSettings):
        self.settings = settings
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def list(self, actor: User) -> list[LLMConfigView]:
        with self._session_factory() as db:
            return [self._view(item) for item in db.scalars(
                select(UserLLMConfig).where(UserLLMConfig.user_id == actor.id).order_by(UserLLMConfig.updated_at.desc())
            )]

    def defaults(self, actor: User) -> dict[str, object]:
        with self._session_factory() as db:
            item = db.get(UserLLMDefaults, actor.id)
            values = dict(DEFAULT_OPTIONS)
            if item:
                values.update(json.loads(item.options))
            return values

    def save_defaults(self, actor: User, options: dict[str, object]) -> dict[str, object]:
        values = dict(DEFAULT_OPTIONS)
        values.update(options)
        now = _now()
        with self._session_factory() as db:
            item = db.get(UserLLMDefaults, actor.id)
            if item is None:
                db.add(UserLLMDefaults(user_id=actor.id, options=json.dumps(values), updated_at=now))
            else:
                item.options = json.dumps(values)
                item.updated_at = now
            db.commit()
        return values

    def save(self, actor: User, payload: dict[str, object], config_id: str | None = None) -> LLMConfigView:
        name = str(payload["name"]).strip()
        base_url = str(payload["base_url"]).strip().rstrip("/")
        model_name = str(payload["model_name"]).strip()
        if not name or not base_url or not model_name:
            raise ValueError("配置名称、Base URL、模型名不能为空")
        if payload.get("api_type") not in {"openai", "anthropic"}:
            raise ValueError("API 类型不支持")
        now = _now()
        with self._session_factory() as db:
            item = db.get(UserLLMConfig, config_id) if config_id else None
            if item and item.user_id != actor.id:
                raise ValueError("配置不存在")
            if item is None:
                item = UserLLMConfig(
                    id=str(uuid4()),
                    user_id=actor.id,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                db.add(item)
            else:
                item.version += 1
            item.name = name
            item.description = str(payload.get("description") or "")
            item.base_url = base_url
            item.api_type = str(payload.get("api_type") or "openai")
            item.model_name = model_name
            item.enabled = bool(payload.get("enabled", True))
            item.advanced_options = json.dumps(payload.get("advanced_options") or {})
            api_key = payload.get("api_key")
            if api_key:
                item.api_key_ciphertext = CredentialCipher(self.settings.credential_encryption_key).encrypt(str(api_key))
            item.updated_at = now
            db.commit()
            return self._view(item)

    def delete(self, actor: User, config_id: str) -> None:
        with self._session_factory() as db:
            item = db.get(UserLLMConfig, config_id)
            if item is None or item.user_id != actor.id:
                raise ValueError("配置不存在")
            db.delete(item)
            db.commit()

    def test_connection(self, actor: User, config_id: str) -> dict[str, object]:
        connection = self.connection(actor, config_id)
        started = time.perf_counter()
        try:
            probe(connection)
            status = "success"
            available = True
            detail = "OK"
        except ValueError as exc:
            status = "failed"
            available = False
            detail = str(exc)
        latency = round((time.perf_counter() - started) * 1000)
        with self._session_factory() as db:
            item = db.get(UserLLMConfig, config_id)
            if item is None or item.user_id != actor.id:
                raise ValueError("配置不存在")
            item.available = available
            item.last_test_status = status
            item.last_test_latency_ms = latency
            item.updated_at = _now()
            db.commit()
            return {"status": status, "available": available, "latency_ms": latency, "detail": detail}

    def connection(self, actor: User | str, config_id: str) -> dict[str, object]:
        actor_id = actor.id if isinstance(actor, User) else actor
        with self._session_factory() as db:
            item = db.get(UserLLMConfig, config_id)
            if item is None or item.user_id != actor_id:
                raise ValueError("配置不存在")
            key = CredentialCipher(self.settings.credential_encryption_key).decrypt(item.api_key_ciphertext) if item.api_key_ciphertext else None
            defaults_actor = actor if isinstance(actor, User) else db.get(User, actor_id)
            advanced = dict(self.defaults(defaults_actor)) if defaults_actor else dict(DEFAULT_OPTIONS)
            advanced.update(json.loads(item.advanced_options or "{}"))
            return {"base_url": item.base_url, "api_type": item.api_type, "model_name": item.model_name, "api_key": key, "advanced_options": advanced}

    def _view(self, item: UserLLMConfig) -> LLMConfigView:
        masked_api_key = None
        if item.api_key_ciphertext:
            masked_api_key = mask_credential(
                CredentialCipher(self.settings.credential_encryption_key).decrypt(
                    item.api_key_ciphertext
                )
            )
        return LLMConfigView(
            id=item.id, name=item.name, description=item.description, base_url=item.base_url,
            api_type=item.api_type, model_name=item.model_name, has_api_key=bool(item.api_key_ciphertext),
            masked_api_key=masked_api_key,
            enabled=item.enabled, available=item.available, last_test_status=item.last_test_status,
            last_test_latency_ms=item.last_test_latency_ms, advanced_options=json.loads(item.advanced_options or "{}"),
            version=item.version, created_at=item.created_at, updated_at=item.updated_at,
        )


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)
