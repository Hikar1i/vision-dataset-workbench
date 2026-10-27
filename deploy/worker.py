"""Wait for first-time setup in the shared home, then replace this process with Worker."""
import os
import time

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.worker import _workspace

settings = RuntimeSettings.from_env()
print("Worker waiting for workspace initialization", flush=True)
while True:
    try:
        _workspace(settings)
        break
    except SystemExit:
        time.sleep(2)
os.execvp("python", ["python", "-m", "vision_dataset_workbench.worker"])
