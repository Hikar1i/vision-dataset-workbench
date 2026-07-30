import json
import os
import shutil
import time
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .dataset_export import dataset_yaml, safe_export_name, split_videos, yolo_line
from .models import (
    DatasetExport,
    Frame,
    FrameAnnotation,
    SamplingPlan,
    Task,
    Video,
)


class DatasetExportTaskCanceled(RuntimeError):
    pass


def _group_by(items: list[Any], key: Callable[[Any], str]) -> dict[str, list[Any]]:
    grouped: dict[str, list[Any]] = defaultdict(list)
    for item in items:
        grouped[key(item)].append(item)
    return dict(grouped)


def _exclusion_reason(video: Video, plan: SamplingPlan | None, enabled_frames: int) -> str:
    if not video.enabled:
        return "video_disabled"
    if video.status != "ready":
        return "video_not_ready"
    if plan is None or plan.extracted_frames == 0:
        return "no_sampled_frames"
    if enabled_frames == 0:
        return "no_enabled_frames"
    return "created_after_export"


def execute_dataset_export(
    session_factory: sessionmaker[Session],
    workspace: Path,
    task_id: str,
    task_temp: Path,
    now: Callable[[], datetime],
    heartbeat: Callable[[str, int | None], None],
    cancel_requested: Callable[[str], bool],
) -> None:
    started_at = now()
    with session_factory() as database:
        task = database.get(Task, task_id)
        if task is None or task.status != "running":
            raise RuntimeError("active dataset export task not found")
        export_id = str(json.loads(task.payload).get("export_id") or "")
        record = database.get(DatasetExport, export_id)
        if record is None or record.task_id != task_id or record.status not in {"queued", "running"}:
            raise RuntimeError("dataset export record not found")
        record.status = "running"
        record.started_at = record.started_at or started_at
        labels = json.loads(record.label_snapshot)
        source_snapshot = json.loads(record.source_snapshot)
        project_id = record.project_id
        train_ratio = record.train_ratio
        export_name = record.name
        created_at = record.created_at
        payload = json.loads(task.payload)
        exports_root = workspace / "projects" / project_id / "exports"
        exports_root.mkdir(parents=True, exist_ok=True)
        directory_name = str(payload.get("directory_name") or "")
        if not directory_name:
            timestamp = time.strftime("%Y%m%d%H%M%S")
            base_name = f"{safe_export_name(export_name)}_{timestamp}"
            directory_name = base_name
            suffix = 2
            while (exports_root / directory_name).exists():
                directory_name = f"{base_name}_{suffix}"
                suffix += 1
            payload["directory_name"] = directory_name
            task.payload = json.dumps(payload, ensure_ascii=False)
        database.commit()

    target = exports_root / directory_name
    if target.exists():
        shutil.rmtree(target)

    with session_factory() as database:
        videos = list(
            database.scalars(
                select(Video)
                .where(Video.project_id == project_id)
                .order_by(Video.id)
            )
        )
        video_ids = [video.id for video in videos]
        plans = {
            plan.video_id: plan
            for plan in database.scalars(
                select(SamplingPlan).where(SamplingPlan.video_id.in_(video_ids))
            )
        }
        frames = list(
            database.scalars(
                select(Frame)
                .where(Frame.video_id.in_(video_ids))
                .order_by(Frame.video_id, Frame.sequence)
            )
        ) if video_ids else []
        frame_ids = [frame.id for frame in frames]
        annotations = list(
            database.scalars(
                select(FrameAnnotation)
                .where(FrameAnnotation.frame_id.in_(frame_ids))
                .order_by(
                    FrameAnnotation.frame_id,
                    FrameAnnotation.sort_order,
                    FrameAnnotation.id,
                )
            )
        ) if frame_ids else []

    videos_by_id = {video.id: video for video in videos}
    frames_by_video = _group_by(frames, lambda item: item.video_id)
    annotations_by_frame = _group_by(annotations, lambda item: item.frame_id)
    snapshot_items = source_snapshot.get("videos", [])
    snapshot_by_video = {str(item["video_id"]): item for item in snapshot_items}
    frame_counts: dict[str, int] = {}
    for video_id, snapshot in snapshot_by_video.items():
        video = videos_by_id.get(video_id)
        plan = plans.get(video_id)
        if video is None or plan is None:
            raise RuntimeError("dataset export source video disappeared")
        if (
            video.version != snapshot["video_version"]
            or plan.generation != snapshot["sampling_generation"]
            or plan.frame_revision != snapshot["frame_revision"]
        ):
            raise RuntimeError("dataset export source changed")
        current_frames = [
            frame
            for frame in frames_by_video.get(video_id, [])
            if frame.generation == plan.generation and frame.enabled
        ]
        if len(current_frames) != snapshot["enabled_frames"]:
            raise RuntimeError("dataset export source frame count changed")
        frame_counts[video_id] = len(current_frames)

    train_video_ids, val_video_ids = split_videos(frame_counts, train_ratio)
    train_ids = set(train_video_ids)
    val_ids = set(val_video_ids)
    enabled_labels = {
        str(item["source_label_id"]): int(item["mapping"])
        for item in labels
        if item["enabled"]
    }
    all_label_ids = {str(item["source_label_id"]) for item in labels}
    staged = task_temp / "dataset"
    for split in ("train", "val"):
        (staged / split / "images").mkdir(parents=True)
        (staged / split / "labels").mkdir(parents=True)

    total_frames = sum(frame_counts.values())
    processed = 0
    last_progress = -1
    project_frames_root = (workspace / "projects" / project_id / "frames").resolve()
    for video_id in sorted(snapshot_by_video):
        video = videos_by_id[video_id]
        plan = plans[video_id]
        split = "train" if video_id in train_ids else "val"
        for frame in frames_by_video.get(video_id, []):
            if frame.generation != plan.generation or not frame.enabled:
                continue
            if cancel_requested(task_id):
                raise DatasetExportTaskCanceled("task canceled")
            source = (workspace / frame.file_path).resolve(strict=True)
            expected_root = (project_frames_root / video.short_code).resolve()
            if not source.is_file() or not source.is_relative_to(expected_root):
                raise RuntimeError("dataset export frame path is invalid")
            image_target = staged / split / "images" / source.name
            label_target = staged / split / "labels" / f"{source.stem}.txt"
            if image_target.exists() or label_target.exists():
                raise RuntimeError("dataset export frame filename collision")
            os.link(source, image_target)
            lines = []
            for annotation in annotations_by_frame.get(frame.id, []):
                if annotation.label_id not in all_label_ids:
                    raise RuntimeError("dataset export annotation label is outside snapshot")
                class_id = enabled_labels.get(annotation.label_id)
                if class_id is None:
                    continue
                lines.append(
                    yolo_line(
                        class_id,
                        (
                            annotation.x_min,
                            annotation.y_min,
                            annotation.x_max,
                            annotation.y_max,
                        ),
                        video.width,
                        video.height,
                    )
                )
            label_target.write_text("\n".join(lines) + ("\n" if lines else ""))
            processed += 1
            progress = round(processed * 95 / total_frames) if total_frames else 95
            if progress > last_progress:
                heartbeat(task_id, progress)
                last_progress = progress

    video_stats = []
    for video in videos:
        plan = plans.get(video.id)
        current_frames = [
            frame
            for frame in frames_by_video.get(video.id, [])
            if plan is not None and frame.generation == plan.generation
        ]
        enabled = [frame for frame in current_frames if frame.enabled]
        positive = sum(
            any(
                item.label_id in enabled_labels
                for item in annotations_by_frame.get(frame.id, [])
            )
            for frame in enabled
        )
        split = (
            "train"
            if video.id in train_ids
            else "val"
            if video.id in val_ids
            else "excluded"
        )
        video_stats.append(
            {
                "video_id": video.id,
                "video_short_code": video.short_code,
                "title": video.title,
                "split": split,
                "exclusion_reason": (
                    None
                    if split != "excluded"
                    else _exclusion_reason(video, plan, len(enabled))
                ),
                "total_frames": len(current_frames),
                "enabled_frames": len(enabled),
                "disabled_frames": len(current_frames) - len(enabled),
                "positive_frames": positive,
                "negative_frames": len(enabled) - positive,
            }
        )

    train_frames = sum(frame_counts[video_id] for video_id in train_video_ids)
    val_frames = total_frames - train_frames
    actual_train_ratio = train_frames / total_frames if total_frames else 0
    completed_at = now()
    manifest = {
        "version": 1,
        "export_id": export_id,
        "name": export_name,
        "created_at": f"{created_at.isoformat(timespec='seconds')}Z",
        "completed_at": f"{completed_at.isoformat(timespec='seconds')}Z",
        "expected_train_ratio": train_ratio,
        "actual_train_ratio": actual_train_ratio,
        "actual_val_ratio": 1 - actual_train_ratio,
        "total_frames": total_frames,
        "train_frames": train_frames,
        "val_frames": val_frames,
        "labels": labels,
        "train_video_ids": train_video_ids,
        "val_video_ids": val_video_ids,
        "disabled_video_ids": [video.id for video in videos if not video.enabled],
        "video_stats": video_stats,
    }
    manifest_text = json.dumps(manifest, ensure_ascii=False, indent=2) + "\n"
    (staged / "classes.txt").write_text(
        "\n".join(str(item["name"]) for item in labels) + "\n"
    )
    (staged / "dataset.yaml").write_text(
        dataset_yaml([str(item["name"]) for item in labels])
    )
    (staged / "manifest.json").write_text(manifest_text)
    for split, expected in (("train", train_frames), ("val", val_frames)):
        if (
            len(list((staged / split / "images").iterdir())) != expected
            or len(list((staged / split / "labels").iterdir())) != expected
        ):
            raise RuntimeError("dataset export validation failed")
    if cancel_requested(task_id):
        raise DatasetExportTaskCanceled("task canceled")
    os.replace(staged, target)
    try:
        with session_factory() as database:
            task = database.get(Task, task_id)
            record = database.get(DatasetExport, export_id)
            if task is None or task.status != "running" or record is None:
                raise RuntimeError("dataset export resources disappeared")
            record.status = "ready"
            record.actual_train_ratio = actual_train_ratio
            record.total_frames = total_frames
            record.train_frames = train_frames
            record.val_frames = val_frames
            record.manifest = manifest_text
            record.storage_path = target.relative_to(workspace).as_posix()
            record.error = None
            record.completed_at = completed_at
            task.status = "succeeded"
            task.progress = 100
            task.result = json.dumps(
                {"outcome": "exported", "export_id": export_id, "frames": total_frames}
            )
            task.error = None
            task.finished_at = completed_at
            task.updated_at = completed_at
            task.lease_owner = None
            task.lease_expires_at = None
            database.commit()
    except Exception:
        shutil.rmtree(target, ignore_errors=True)
        raise
