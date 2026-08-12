import json
import re
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = 1
EVENT_TYPES = {
    "started",
    "progress",
    "epoch_end",
    "artifact",
    "warning",
    "completed",
    "failed",
}
ANSI_ESCAPE = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


class EventWriter:
    def __init__(self, path: Path, run_id: str, token: str):
        self.path, self.run_id, self.token, self.sequence = path, run_id, token, 0

    def write(self, event_type: str, **payload: object) -> None:
        if event_type not in EVENT_TYPES:
            raise ValueError("unknown training event")
        self.sequence += 1
        event = {
            "schema_version": SCHEMA_VERSION,
            "run_id": self.run_id,
            "token": self.token,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "sequence": self.sequence,
            "type": event_type,
            **payload,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(event, ensure_ascii=False, allow_nan=False) + "\n")
            output.flush()


def validate_event(
    value: object, *, run_id: str, token: str, last_sequence: int
) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("invalid training event schema")
    if value.get("run_id") != run_id or value.get("token") != token:
        raise ValueError("training event identity mismatch")
    sequence = value.get("sequence")
    if not isinstance(sequence, int) or sequence != last_sequence + 1:
        raise ValueError("training event sequence mismatch")
    if value.get("type") not in EVENT_TYPES:
        raise ValueError("unknown training event")
    return value


def terminal_snapshot(path: Path, maximum_bytes: int = 256_000) -> tuple[str, int]:
    """Return a bounded terminal-like view where carriage returns overwrite a line."""
    size = path.stat().st_size
    with path.open("rb") as stream:
        stream.seek(max(0, size - maximum_bytes))
        raw = stream.read()
    text = ANSI_ESCAPE.sub("", raw.decode("utf-8", errors="replace"))
    lines: list[str] = []
    current = ""
    for character in text:
        if character == "\r":
            current = ""
        elif character == "\n":
            lines.append(current)
            current = ""
        elif character == "\b":
            current = current[:-1]
        elif character == "\t" or character >= " ":
            current += character
    if current:
        lines.append(current)
    return "\n".join(lines[-2000:]), size
