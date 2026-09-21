import os
from dataclasses import dataclass
from pathlib import Path
from typing import Literal


class InvalidRuntimeSettings(ValueError):
    pass


@dataclass(frozen=True)
class RuntimeSettings:
    home: Path
    workspace: Path | None
    app_mode: Literal["multi", "single"] = "multi"
    ytdlp_proxy: str | None = None
    ytdlp_cookie_file: Path | None = None
    credential_encryption_key: str | None = None

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        home = Path.home().resolve()
        raw_workspace = os.environ.get("VDW_WORKSPACE")
        workspace = Path(raw_workspace).expanduser().resolve() if raw_workspace else None
        mode = os.environ.get("APP_MODE", "multi")
        if mode not in {"multi", "single"}:
            raise InvalidRuntimeSettings("APP_MODE must be multi or single")
        return cls(
            home=home,
            workspace=workspace,
            app_mode=mode,
            ytdlp_proxy=os.environ.get("YTDLP_PROXY") or None,
            ytdlp_cookie_file=(
                Path(cookie_file).expanduser().resolve()
                if (cookie_file := os.environ.get("YTDLP_COOKIE_FILE"))
                else None
            ),
            credential_encryption_key=(
                os.environ.get("VDW_CREDENTIAL_ENCRYPTION_KEY") or None
            ),
        )
