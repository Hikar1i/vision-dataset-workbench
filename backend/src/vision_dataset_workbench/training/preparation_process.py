import argparse
import json
import os
import time
import traceback
from pathlib import Path

from .dataset_preparation import materialize_snapshot
from .events import EventWriter


def run(spec_path: Path, events_path: Path) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    writer = EventWriter(events_path, str(spec["preparation_id"]), str(spec["token"]))
    workspace = Path(str(spec["workspace"]))
    snapshots = list(spec["snapshots"])
    total = sum(int(item.get("total_frames") or 0) for item in snapshots)
    completed = 0
    last_emitted = 0.0

    def report(phase: str, processed: int, _snapshot_total: int) -> None:
        nonlocal last_emitted
        now = time.monotonic()
        current = completed + processed
        if current != total and current % 500 and now - last_emitted < 1:
            return
        writer.write("progress", phase=phase, processed=current, total=total)
        print(f"[prepare] {phase} {current}/{total}", flush=True)
        last_emitted = now

    try:
        writer.write("started", pid=os.getpid(), total=total)
        print(f"[prepare] validate {len(snapshots)} unique dataset configs", flush=True)
        artifacts: dict[str, object] = {}
        for item in snapshots:
            snapshot = dict(item["snapshot"])
            target = workspace / str(item["storage_path"])
            stats = materialize_snapshot(snapshot, workspace, target, report)
            artifacts[str(item["config_hash"])] = {
                "storage_path": str(item["storage_path"]),
                "stats": stats,
            }
            completed += int(item.get("total_frames") or stats["images"])
            writer.write(
                "artifact",
                config_hash=item["config_hash"],
                storage_path=item["storage_path"],
                stats=stats,
            )
        writer.write("completed", artifacts=artifacts)
        print("[prepare] completed", flush=True)
        return 0
    except Exception as exc:
        traceback.print_exc()
        writer.write("failed", error=f"{type(exc).__name__}: {exc}"[:2000])
        return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.spec, args.events))


if __name__ == "__main__":
    main()
