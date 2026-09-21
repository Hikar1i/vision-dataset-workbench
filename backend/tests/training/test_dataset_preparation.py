import json
import os

import pytest

from vision_dataset_workbench.training.dataset_preparation import (
    materialize_snapshot,
    normalize_multi_dataset_config,
    rewrite_yolo_text,
    snapshot_hash,
    source_classes,
)


def test_normalize_config_groups_exact_trimmed_names_case_sensitively():
    value = normalize_multi_dataset_config(
        {
            "version": 1,
            "dataset_export_ids": [" export-a ", "export-b"],
            "target_classes": [" car ", "Car"],
        }
    )
    assert value == {
        "version": 1,
        "dataset_export_ids": ["export-a", "export-b"],
        "target_classes": ["car", "Car"],
    }
    assert source_classes(
        {
            "labels": [
                {"name": " car ", "mapping": 0, "enabled": True},
                {"name": "ignored", "mapping": 1, "enabled": False},
                {"name": "Car", "mapping": 2, "enabled": True},
            ]
        }
    ) == [(0, "car"), (2, "Car")]


@pytest.mark.parametrize(
    "value,message",
    [
        ({"version": 2, "dataset_export_ids": ["a"], "target_classes": ["car"]}, "version"),
        ({"version": 1, "dataset_export_ids": [], "target_classes": ["car"]}, "dataset"),
        (
            {"version": 1, "dataset_export_ids": ["a"], "target_classes": ["car", "car"]},
            "unique",
        ),
    ],
)
def test_normalize_config_rejects_invalid_values(value, message):
    with pytest.raises(ValueError, match=message):
        normalize_multi_dataset_config(value)


def test_rewrite_yolo_label_changes_only_class_column_and_drops_excluded_rows():
    source = "0 0.100000 0.200000 0.300000 0.400000\n1 0.5 0.6 0.7 0.8\n"
    rewritten, dropped = rewrite_yolo_text(source, {0: 2})
    assert rewritten == "2 0.100000 0.200000 0.300000 0.400000\n"
    assert dropped == 1


def test_config_hash_is_stable_for_identical_ordered_config():
    left = {"version": 1, "dataset_export_ids": ["a", "b"], "target_classes": ["car"]}
    assert snapshot_hash(left) == snapshot_hash(dict(reversed(list(left.items()))))
    assert snapshot_hash(left) != snapshot_hash({**left, "dataset_export_ids": ["b", "a"]})


def _source(workspace, export_id, split, labels):
    root = workspace / "exports" / export_id
    (root / split / "images").mkdir(parents=True, exist_ok=True)
    (root / split / "labels").mkdir(parents=True, exist_ok=True)
    (root / "dataset.yaml").write_text("path: .\n", encoding="utf-8")
    for index, label in enumerate(labels):
        (root / split / "images" / f"frame-{index}.jpg").write_bytes(b"image")
        (root / split / "labels" / f"frame-{index}.txt").write_text(label, encoding="utf-8")
    return root


def test_materialize_hardlinks_images_preserves_splits_and_empty_negative_labels(tmp_path):
    workspace = tmp_path / "workspace"
    source_a = _source(
        workspace,
        "export-a",
        "train",
        ["0 0.1 0.2 0.3 0.4\n1 0.5 0.6 0.7 0.8\n", "1 0.1 0.2 0.3 0.4\n"],
    )
    _source(workspace, "export-b", "val", ["0 0.2 0.3 0.4 0.5\n"])
    snapshot = {
        "kind": "multi",
        "target_classes": ["car", "plane"],
        "sources": [
            {
                "dataset_export_id": "export-a",
                "storage_path": "exports/export-a",
                "class_map": {"0": 1},
            },
            {
                "dataset_export_id": "export-b",
                "storage_path": "exports/export-b",
                "class_map": {"0": 0},
            },
        ],
    }
    calls = []
    target = workspace / "training" / "tasks" / "task" / "datasets" / "hash"
    stats = materialize_snapshot(snapshot, workspace, target, lambda *args: calls.append(args))

    linked = target / "train/images/export-a_frame-0.jpg"
    assert os.stat(linked).st_ino == os.stat(source_a / "train/images/frame-0.jpg").st_ino
    assert (target / "train/labels/export-a_frame-0.txt").read_text() == (
        "1 0.1 0.2 0.3 0.4\n"
    )
    assert (target / "train/labels/export-a_frame-1.txt").read_text() == ""
    assert (target / "val/images/export-b_frame-0.jpg").is_file()
    assert stats == {
        "images": 3,
        "annotations": 2,
        "ignored_annotations": 2,
        "negative_images": 1,
    }
    assert json.loads((target / "manifest.json").read_text())["stats"] == stats
    assert (target / "READY").is_file()
    assert calls[-1] == ("validate", 3, 3)
