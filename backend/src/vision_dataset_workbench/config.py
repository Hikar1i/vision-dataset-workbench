import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeSettings:
    home: Path
    workspace: Path | None
    ytdlp_proxy: str | None = None
    ytdlp_cookie_file: Path | None = None
    credential_encryption_key: str | None = None

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        home = Path.home().resolve()
        raw_workspace = os.environ.get("VDW_WORKSPACE")
        workspace = Path(raw_workspace).expanduser().resolve() if raw_workspace else None
        return cls(
            home=home,
            workspace=workspace,
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
