import argparse
import json
import os
import time
from pathlib import Path

from .events import EventWriter
from .curves import precision_recall_payload


def _fake(spec: dict[str, object], writer: EventWriter, output: Path) -> None:
    epochs = int(spec["parameters"]["epochs"])  # type: ignore[index]
    delay = float(spec.get("fake_epoch_delay", 0.01))
    fail_at = int(spec.get("fake_fail_at", 0))
    writer.write("started", pid=os.getpid())
    for epoch in range(1, epochs + 1):
        time.sleep(delay)
        if fail_at == epoch:
            raise RuntimeError(f"fake failure at epoch {epoch}")
        ratio = epoch / epochs
        writer.write(
            "epoch_end",
            epoch=epoch,
            metrics={
                "box_loss": 1 / epoch,
                "cls_loss": 0.8 / epoch,
                "learning_rate": 0.01 * (1 - ratio),
                "precision": ratio * 0.9,
                "recall": ratio * 0.8,
                "map50": ratio * 0.85,
                "map50_95": ratio * 0.65,
            },
        )
    weights = output / "weights"
    weights.mkdir(parents=True, exist_ok=True)
    (weights / "best.pt").write_bytes(b"fake-yolo-best")
    (weights / "last.pt").write_bytes(b"fake-yolo-last")
    (output / "pr-curve.json").write_text(
        json.dumps(
            {
                "version": 1,
                "kind": "interactive",
                "series": [{"name": "all", "points": [[0, 1], [0.5, 0.85], [1, 0.2]]}],
            }
        ),
        encoding="utf-8",
    )
    writer.write("artifact", best="weights/best.pt", last="weights/last.pt")
    writer.write("completed")


def _real(spec: dict[str, object], writer: EventWriter, output: Path) -> None:
    from ultralytics import YOLO

    writer.write("started", pid=os.getpid())
    model = YOLO(str(spec["base_model"]))
    parameters = dict(spec["parameters"])  # type: ignore[arg-type]

    def epoch_end(trainer) -> None:
        epoch = int(trainer.epoch) + 1
        source = dict(getattr(trainer, "metrics", {}) or {})
        losses = getattr(trainer, "loss_items", None)
        writer.write(
            "epoch_end",
            epoch=epoch,
            metrics={
                "box_loss": float(losses[0]) if losses is not None and len(losses) > 0 else None,
                "cls_loss": float(losses[1]) if losses is not None and len(losses) > 1 else None,
                "learning_rate": float(trainer.optimizer.param_groups[0]["lr"]),
                "precision": source.get("metrics/precision(B)"),
                "recall": source.get("metrics/recall(B)"),
                "map50": source.get("metrics/mAP50(B)"),
                "map50_95": source.get("metrics/mAP50-95(B)"),
            },
        )

    model.add_callback("on_fit_epoch_end", epoch_end)

    def train_end(trainer) -> None:
        payload = precision_recall_payload(getattr(trainer, "validator", None))
        if payload:
            (output / "pr-curve.json").write_text(
                json.dumps(payload, ensure_ascii=False, allow_nan=False), encoding="utf-8"
            )

    model.add_callback("on_train_end", train_end)
    if spec.get("resume") is True:
        model.train(resume=True, device=int(spec["gpu_index"]))
    else:
        model.train(
            data=str(spec["dataset_yaml"]),
            project=str(output.parent),
            name=output.name,
            exist_ok=True,
            device=int(spec["gpu_index"]),
            **parameters,
        )
    best, last = output / "weights" / "best.pt", output / "weights" / "last.pt"
    writer.write(
        "artifact",
        best="weights/best.pt" if best.is_file() else None,
        last="weights/last.pt" if last.is_file() else None,
    )
    writer.write("completed")


def run(spec_path: Path, events_path: Path) -> int:
    spec = json.loads(spec_path.read_text(encoding="utf-8"))
    output = Path(spec["output"])
    output.mkdir(parents=True, exist_ok=True)
    writer = EventWriter(events_path, str(spec["run_id"]), str(spec["token"]))
    try:
        if spec.get("fake") is True:
            _fake(spec, writer, output)
        else:
            _real(spec, writer, output)
        return 0
    except BaseException as exc:
        writer.write("failed", error=str(exc)[:2000])
        return 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--spec", type=Path, required=True)
    parser.add_argument("--events", type=Path, required=True)
    args = parser.parse_args()
    raise SystemExit(run(args.spec, args.events))


if __name__ == "__main__":
    main()
