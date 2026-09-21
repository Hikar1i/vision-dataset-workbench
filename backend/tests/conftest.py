import os
from pathlib import Path


# Module-level FastAPI app creation must never discover and migrate a developer workspace.
os.environ["VDW_WORKSPACE"] = str(Path(__file__).parent / ".unconfigured-workspace")
