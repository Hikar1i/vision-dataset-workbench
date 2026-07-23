import json
import os
from pathlib import Path


def default_locator_path(home: Path, environ: dict[str, str] | None = None) -> Path:
    env = environ if environ is not None else os.environ
    if os.name == "nt":
        root = Path(env.get("APPDATA", home / "AppData" / "Roaming"))
    else:
        root = Path(env.get("XDG_CONFIG_HOME", home / ".config"))
    return root / "vision-dataset-workbench" / "instance.json"


class WorkspaceLocator:
    def __init__(self, path: Path):
        self.path = path

    def read(self) -> Path | None:
        if not self.path.exists():
            return None
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return Path(data["workspace"]).expanduser().resolve()

    def write(self, workspace: Path) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"workspace": str(workspace.resolve())}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.path)
