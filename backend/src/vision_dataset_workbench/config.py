import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimeSettings:
    home: Path
    workspace: Path | None

    @classmethod
    def from_env(cls) -> "RuntimeSettings":
        home = Path.home().resolve()
        raw_workspace = os.environ.get("VDW_WORKSPACE")
        workspace = Path(raw_workspace).expanduser().resolve() if raw_workspace else None
        return cls(home=home, workspace=workspace)
