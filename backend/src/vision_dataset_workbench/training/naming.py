import re
from datetime import date

TASK_CODE = re.compile(r"^[a-z][a-z0-9-]{2,31}$")


def validate_task_code(value: str) -> str:
    value = value.strip().lower()
    if not TASK_CODE.fullmatch(value):
        raise ValueError("task code must be 3-32 lowercase letters, numbers or hyphens")
    return value


def safe_base_code(value: str) -> str:
    clean = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (clean or "yolo")[:32]


def batch_code(mode: str, value: float | None) -> str:
    if mode == "auto":
        return "auto"
    if mode == "fraction":
        return f"p{int(round((value or 0) * 100))}"
    return str(int(value or 0))


def build_artifact_code(
    *,
    task_code: str,
    training_date: date,
    gpu_index: int,
    queue_order: int,
    base_code: str,
    image_size: int,
    batch_mode: str,
    batch_value: float | None,
    epochs: int,
) -> str:
    return (
        f"{validate_task_code(task_code)}-{training_date:%y%m%d}-g{gpu_index}"
        f"-q{queue_order:02d}-{safe_base_code(base_code)}-s{image_size}"
        f"-b{batch_code(batch_mode, batch_value)}-e{epochs}"
    )
