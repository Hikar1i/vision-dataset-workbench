import json
from datetime import date
from types import SimpleNamespace

import pytest

from vision_dataset_workbench.training.actions import model_actions, task_actions
from vision_dataset_workbench.training.curves import precision_recall_payload
from vision_dataset_workbench.training.events import EventWriter, terminal_snapshot, validate_event
from vision_dataset_workbench.training.naming import build_artifact_code, validate_task_code
from vision_dataset_workbench.training.retention import cleanup_intermediate_checkpoints
from vision_dataset_workbench.training.state import aggregate_progress, aggregate_task_state
from vision_dataset_workbench.training.telemetry import memory_level, training_telemetry


def test_artifact_name_exposes_frozen_core_parameters():
    assert (
        build_artifact_code(
            task_code="firedet",
            training_date=date(2026, 8, 4),
            gpu_index=0,
            queue_order=1,
            base_code="YOLO11s.pt",
            image_size=640,
            batch_mode="fixed",
            batch_value=16,
            epochs=200,
        )
        == "firedet-260804-g0-q01-yolo11s-pt-s640-b16-e200"
    )
    with pytest.raises(ValueError):
        validate_task_code("Fire Det")
    assert build_artifact_code(
        task_code="firedet",
        training_date=date(2026, 8, 4),
        gpu_index=1,
        queue_order=2,
        base_code="yolo11n",
        image_size=640,
        batch_mode="fraction",
        batch_value=0.8,
        epochs=100,
    ).endswith("-s640-b80pct-e100")


def test_task_state_and_lifecycle_actions_are_explicit():
    models = [
        SimpleNamespace(status="succeeded", progress=100),
        SimpleNamespace(status="failed", progress=40),
    ]
    assert aggregate_task_state(models) == "partial"
    assert aggregate_progress(models) == 70
    actions = model_actions("failed", has_last=True, has_best=False)
    assert actions["retry"].allowed and actions["resume"].allowed and actions["derive"].allowed
    assert not actions["extend"].allowed
    task = task_actions("partial", ["succeeded", "failed"], has_resumable=True)
    assert task["retry"].allowed and task["resume"].allowed and task["derive"].allowed
    assert not task["start"].allowed and not task["cancel"].allowed


def test_event_identity_sequence_and_retention(tmp_path):
    path = tmp_path / "events.jsonl"
    writer = EventWriter(path, "run", "token")
    writer.write("started", pid=123)
    event = json.loads(path.read_text())
    assert validate_event(event, run_id="run", token="token", last_sequence=0)["type"] == "started"
    with pytest.raises(ValueError):
        validate_event(event, run_id="run", token="wrong", last_sequence=0)
    weights = tmp_path / "weights"
    weights.mkdir()
    for name in ("best.pt", "last.pt", "epoch1.pt", "epoch20.pt"):
        (weights / name).write_bytes(b"x")
    assert cleanup_intermediate_checkpoints(tmp_path) == ["epoch1.pt", "epoch20.pt"]
    assert (weights / "best.pt").is_file() and (weights / "last.pt").is_file()


def test_terminal_snapshot_overwrites_progress_lines(tmp_path):
    path = tmp_path / "train.log"
    path.write_bytes(b"epoch 1 10%\repoch 1 80%\repoch 1 100%\n\x1b[32mdone\x1b[0m\n")
    content, cursor = terminal_snapshot(path)
    assert content == "epoch 1 100%\ndone"
    assert cursor == path.stat().st_size


def test_telemetry_reports_dynamic_memory_levels():
    class Result:
        stdout = "0, RTX A4000, 16384, 2048, 17\n1, RTX 4000, 8192, 7373, 91\n"

    payload = training_telemetry(ttl=0, now=lambda: 1, run=lambda *args, **kwargs: Result())
    assert [row["level"] for row in payload["devices"]] == ["green", "red"]
    assert memory_level(60) == "orange" and memory_level(85) == "red"


def test_pr_curve_adapter_is_version_isolated():
    metrics = SimpleNamespace(
        curves=["Precision-Recall(B)"],
        curves_results=[[[0, 0.5, 1], [[1, 0.8, 0.2]], "Recall", "Precision"]],
        ap_class_index=[3],
    )
    validator = SimpleNamespace(
        metrics=metrics,
        names={3: "fire"},
    )
    payload = precision_recall_payload(validator)
    assert payload == {
        "version": 1,
        "kind": "interactive",
        "series": [{"name": "fire", "points": [[0.0, 1.0], [0.5, 0.8], [1.0, 0.2]]}],
    }
