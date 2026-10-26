import json
import os
import shutil
from collections import Counter
from pathlib import Path


from .dataset_export import dataset_yaml, safe_export_name, yolo_line
from .image_import import file_digest
from .models import DatasetExport, Task
from .services.images import ImageService
from .services.projects import image_project_write_barrier, touch_project
from .storage.materialize import materialize_immutable_file


def execute_image_export(
    session_factory, workspace, task_id, task_temp, now, heartbeat, cancel, canceled_error
):
    with session_factory() as db:
        task = db.get(Task, task_id)
        record = db.get(DatasetExport, json.loads(task.payload)["export_id"])
        owner = task.lease_owner
        source = json.loads(record.source_snapshot)
        labels = json.loads(record.label_snapshot)
        project_id, export_id = record.project_id, record.id
        record.status, record.started_at = "running", record.started_at or now()
        db.commit()
    target = (
        workspace
        / "projects"
        / project_id
        / "exports"
        / f"{safe_export_name(record.name)}_{export_id}"
    )
    staging = task_temp / "dataset"
    for split in ("train", "val"):
        for part in ("images", "labels"):
            (staging / split / part).mkdir(parents=True)
    mappings = {label["source_label_id"]: label["mapping"] for label in labels if label["enabled"]}
    known = {label["source_label_id"] for label in labels}
    class_counts = {"train": Counter(), "val": Counter()}
    positive = Counter()
    for index, sample in enumerate(source["samples"]):
        if cancel(task_id):
            raise canceled_error("图片导出已取消")
        with session_factory() as db:
            image = ImageService.context(db, project_id, sample["image_id"])
            if (
                image.version != sample["version"]
                or image.annotation_revision != sample["annotation_revision"]
            ):
                raise ValueError("导出图片修订已变化")
            annotations = ImageService.annotations(db, [image.id])
        path = workspace / image.file_path
        root = workspace / "projects" / project_id / "images"
        if (
            path.is_symlink()
            or not path.resolve().is_relative_to(root.resolve())
            or not path.is_file()
        ):
            raise ValueError("导出受管图片不可用")
        split, name = sample["split"], sample["output_name"]
        image_target = staging / split / "images" / name
        materialize_immutable_file(path, image_target)
        if file_digest(image_target) != sample["content_sha256"]:
            raise ValueError(f"图片内容已变化：{sample['file_name']}")
        lines = []
        for a in annotations:
            if a.label_id not in known:
                raise ValueError("标注类别不在冻结清单中")
            if a.label_id in mappings:
                mapping = mappings[a.label_id]
                lines.append(
                    yolo_line(
                        mapping,
                        (a.x_min, a.y_min, a.x_max, a.y_max),
                        sample["width"],
                        sample["height"],
                        continuous=True,
                    )
                )
                class_counts[split][str(mapping)] += 1
        if lines:
            positive[split] += 1
        (staging / split / "labels" / (Path(name).stem + ".txt")).write_text(
            "\n".join(lines) + ("\n" if lines else ""), encoding="utf-8"
        )
        heartbeat(task_id, int((index + 1) * 95 / len(source["samples"])))
    counts = Counter(s["split"] for s in source["samples"])
    total = len(source["samples"])
    completed_at = now()
    manifest = {
        **source,
        "version": 2,
        "export_id": export_id,
        "name": record.name,
        "labels": labels,
        "created_at": record.created_at.isoformat() + "Z",
        "completed_at": completed_at.isoformat() + "Z",
        "expected_train_ratio": record.train_ratio,
        "actual_train_ratio": counts["train"] / total,
        "actual_val_ratio": counts["val"] / total,
        "total_samples": total,
        "train_samples": counts["train"],
        "val_samples": counts["val"],
        "total_frames": total,
        "train_frames": counts["train"],
        "val_frames": counts["val"],
        "class_counts": {k: dict(v) for k, v in class_counts.items()},
        "positive_samples": {split: positive[split] for split in ("train", "val")},
        "negative_samples": {split: counts[split] - positive[split] for split in ("train", "val")},
    }
    text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (staging / "manifest.json").write_text(text, encoding="utf-8")
    (staging / "classes.txt").write_text(
        "\n".join(label["name"] for label in labels) + "\n", encoding="utf-8"
    )
    (staging / "dataset.yaml").write_text(
        dataset_yaml([label["name"] for label in labels]), encoding="utf-8"
    )
    for split in ("train", "val"):
        assert len(list((staging / split / "images").iterdir())) == counts[split]
        assert len(list((staging / split / "labels").iterdir())) == counts[split]
    if cancel(task_id):
        raise canceled_error("图片导出已取消")
    published = False
    try:
        with session_factory() as db:
            image_project_write_barrier(db, project_id, task_id)
            task = db.get(Task, task_id)
            stored = db.get(DatasetExport, export_id)
            if task.status != "running" or task.cancel_requested or task.lease_owner != owner:
                raise canceled_error("图片导出状态或租约已变化")
            if target.exists():
                shutil.rmtree(target)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, target)
            published = True
            stored.status, stored.manifest = "ready", text
            stored.total_frames, stored.train_frames, stored.val_frames = (
                total,
                counts["train"],
                counts["val"],
            )
            stored.actual_train_ratio, stored.completed_at, stored.error = (
                counts["train"] / total,
                completed_at,
                None,
            )
            stored.storage_path = target.relative_to(workspace).as_posix()
            task.status, task.progress, task.error = "succeeded", 100, None
            task.result = json.dumps({"export_id": export_id, "samples": total})
            task.finished_at, task.updated_at = completed_at, completed_at
            task.lease_owner, task.lease_expires_at = None, None
            touch_project(db, project_id, at=completed_at)
            db.commit()
    except Exception:
        if published:
            shutil.rmtree(target, ignore_errors=True)
        raise
