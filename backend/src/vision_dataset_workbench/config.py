import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class InvalidRuntimeSettings(ValueError):
    pass


def _boolean(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    if raw.lower() not in {"true", "false"}:
        raise InvalidRuntimeSettings(f"{name} must be true or false")
    return raw.lower() == "true"


@dataclass(frozen=True)
class RuntimeSettings:
    home: Path
    workspace: Path | None
    app_mode: Literal["multi", "single"] = "multi"
    registration_enabled: bool = False
    ytdlp_proxy: str | None = None
    ytdlp_cookie_file: Path | None = None

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        home = Path.home().resolve()
        raw_workspace = os.environ.get("VDW_WORKSPACE")
        workspace = Path(raw_workspace).expanduser().resolve() if raw_workspace else None
        mode = os.environ.get("APP_MODE", "multi")
        if mode not in {"multi", "single"}:
            raise InvalidRuntimeSettings("APP_MODE must be multi or single")
        registration_enabled = _boolean("REGISTRATION_ENABLED")
        if mode == "single" and registration_enabled:
            raise InvalidRuntimeSettings("REGISTRATION_ENABLED must be false in single mode")
        return cls(
            home=home,
            workspace=workspace,
            app_mode=mode,
            registration_enabled=registration_enabled,
            ytdlp_proxy=os.environ.get("YTDLP_PROXY") or None,
            ytdlp_cookie_file=(
                Path(cookie_file).expanduser().resolve()
                if (cookie_file := os.environ.get("YTDLP_COOKIE_FILE"))
                else None
            ),
        )
