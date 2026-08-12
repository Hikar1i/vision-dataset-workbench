import hashlib
import json
import os
import re
import shutil
from collections.abc import Callable
from pathlib import Path
from uuid import uuid4

from ..dataset_export import dataset_yaml

ProgressCallback = Callable[[str, int, int], None]
YOLO_LINE = re.compile(r"^(?P<prefix>\s*)(?P<class_id>\d+)(?P<rest>\s+.*)?$")


def normalize_multi_dataset_config(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("multi-dataset config version must be 1")
    dataset_ids = value.get("dataset_export_ids")
    class_names = value.get("target_classes")
    if not isinstance(dataset_ids, list) or not dataset_ids:
        raise ValueError("at least one dataset export is required")
    if not isinstance(class_names, list) or not class_names:
        raise ValueError("at least one target class is required")
    clean_ids = [item.strip() for item in dataset_ids if isinstance(item, str)]
    clean_names = [item.strip() for item in class_names if isinstance(item, str)]
    if len(clean_ids) != len(dataset_ids) or any(not item for item in clean_ids):
        raise ValueError("dataset export ids must be non-empty strings")
    if len(clean_names) != len(class_names) or any(not item for item in clean_names):
        raise ValueError("target classes must be non-empty strings")
    if len(set(clean_ids)) != len(clean_ids):
        raise ValueError("dataset export ids must be unique")
    if len(set(clean_names)) != len(clean_names):
        raise ValueError("target classes must be unique")
    if any(len(item) > 128 for item in clean_names):
        raise ValueError("target class is too long")
    return {"version": 1, "dataset_export_ids": clean_ids, "target_classes": clean_names}


def source_classes(manifest: dict[str, object]) -> list[tuple[int, str]]:
    labels = manifest.get("labels")
    if not isinstance(labels, list):
        raise ValueError("dataset manifest labels are missing")
    result: list[tuple[int, str]] = []
    seen: set[int] = set()
    for fallback, item in enumerate(labels):
        if not isinstance(item, dict) or item.get("enabled") is False:
            continue
        name = str(item.get("name") or "").strip()
        source_index = item.get("mapping", fallback)
        if not name or not isinstance(source_index, int) or source_index < 0:
            raise ValueError("dataset manifest label is invalid")
        if source_index in seen:
            raise ValueError("dataset manifest label indexes must be unique")
        seen.add(source_index)
        result.append((source_index, name))
    if not result:
        raise ValueError("dataset manifest has no enabled labels")
    return result


def snapshot_hash(snapshot: dict[str, object]) -> str:
    payload = json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def rewrite_yolo_text(text: str, class_map: dict[int, int]) -> tuple[str, int]:
    output: list[str] = []
    dropped = 0
    for raw in text.splitlines(keepends=True):
        ending = "\r\n" if raw.endswith("\r\n") else "\n" if raw.endswith("\n") else ""
        body = raw[: -len(ending)] if ending else raw
        if not body.strip():
            continue
        match = YOLO_LINE.fullmatch(body)
        if match is None:
            raise ValueError("invalid YOLO label line")
        source_index = int(match.group("class_id"))
        target_index = class_map.get(source_index)
        if target_index is None:
            dropped += 1
            continue
        rest = match.group("rest") or ""
        output.append(f"{match.group('prefix')}{target_index}{rest}{ending}")
    return "".join(output), dropped


def _inside(workspace: Path, value: Path) -> Path:
    resolved = value.resolve()
    if not resolved.is_relative_to(workspace.resolve()):
        raise ValueError("dataset path is outside the workspace")
    return resolved


def materialize_snapshot(
    snapshot: dict[str, object],
    workspace: Path,
    target: Path,
    progress: ProgressCallback | None = None,
) -> dict[str, int]:
    workspace = workspace.resolve()
    target = _inside(workspace, target)
    ready = target / "READY"
    if ready.is_file():
        manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
        return dict(manifest["stats"])
    sources = snapshot.get("sources")
    target_classes = snapshot.get("target_classes")
    if not isinstance(sources, list) or not sources or not isinstance(target_classes, list):
        raise ValueError("multi-dataset snapshot is incomplete")

    source_files: list[tuple[dict[str, object], Path, str, list[Path]]] = []
    total = 0
    for source in sources:
        if not isinstance(source, dict):
            raise ValueError("multi-dataset source is invalid")
        root = _inside(workspace, workspace / str(source.get("storage_path") or ""))
        if not (root / "dataset.yaml").is_file():
            raise ValueError("source dataset is unavailable")
        for split in ("train", "val", "test"):
            image_dir = root / split / "images"
            if not image_dir.is_dir():
                continue
            images = sorted(item for item in image_dir.iterdir() if item.is_file())
            source_files.append((source, root, split, images))
            total += len(images)

    label_bytes = 0
    for _source, root, split, images in source_files:
        for image in images:
            label = root / split / "labels" / f"{image.stem}.txt"
            if not label.is_file():
                raise ValueError(f"source label is missing: {label.name}")
            label_bytes += label.stat().st_size
    required_bytes = 16 * 1024 * 1024 + total * 4096 + label_bytes * 2
    if shutil.disk_usage(workspace).free < required_bytes:
        raise ValueError("insufficient disk space for prepared dataset metadata and labels")
    if progress:
        progress("validate", 0, total)

    staging = target.parent / f".preparing-{uuid4()}"
    stats = {"images": 0, "annotations": 0, "ignored_annotations": 0, "negative_images": 0}
    try:
        staging.mkdir(parents=True)
        splits = {split for _source, _root, split, _images in source_files}
        for split in splits:
            (staging / split / "images").mkdir(parents=True)
            (staging / split / "labels").mkdir(parents=True)
        processed = 0
        for source, root, split, images in source_files:
            export_id = str(source.get("dataset_export_id") or "")
            raw_map = source.get("class_map")
            if not export_id or not isinstance(raw_map, dict):
                raise ValueError("multi-dataset source mapping is invalid")
            class_map = {int(key): int(value) for key, value in raw_map.items()}
            for image in images:
                filename = f"{export_id}_{image.name}"
                image_target = staging / split / "images" / filename
                label_source = root / split / "labels" / f"{image.stem}.txt"
                label_target = staging / split / "labels" / f"{Path(filename).stem}.txt"
                if not label_source.is_file():
                    raise ValueError(f"source label is missing: {label_source.name}")
                os.link(image, image_target)
                rewritten, dropped = rewrite_yolo_text(
                    label_source.read_text(encoding="utf-8"), class_map
                )
                label_target.write_text(rewritten, encoding="utf-8")
                kept = sum(1 for line in rewritten.splitlines() if line.strip())
                stats["images"] += 1
                stats["annotations"] += kept
                stats["ignored_annotations"] += dropped
                stats["negative_images"] += int(kept == 0)
                processed += 1
                if progress:
                    progress("rewrite_labels", processed, total)

        yaml_text = dataset_yaml([str(item) for item in target_classes])
        if "test" in splits:
            yaml_text = yaml_text.replace("val: val/images\n", "val: val/images\ntest: test/images\n")
        (staging / "dataset.yaml").write_text(yaml_text, encoding="utf-8")
        (staging / "classes.txt").write_text(
            "\n".join(str(item) for item in target_classes) + "\n", encoding="utf-8"
        )
        manifest = {"version": 1, "snapshot": snapshot, "stats": stats}
        (staging / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (staging / "READY").write_text("ready\n", encoding="utf-8")
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(staging, target)
        if progress:
            progress("validate", total, total)
        return stats
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise
