"""References that retain exported files, including frozen historical inputs."""

import json
from sqlalchemy import select
from ..models import TrainingTask, TrainingModel


def config_dataset_ids(value):
    payload = json.loads(value or "{}")
    return set(payload.get("dataset_export_ids", []))


def snapshot_dataset_ids(value):
    payload = json.loads(value or "{}")
    ids = {payload.get("dataset_export_id") or payload.get("id")}
    ids.update(source.get("dataset_export_id") for source in payload.get("sources", []))
    return ids - {None, ""}


def reference_count(database, export_ids):
    try:
        return _reference_count(database, export_ids)
    except (ValueError, TypeError, AttributeError) as exc:
        # Unreadable references must never authorize removal of retained files.
        from .projects import ProjectConflict

        raise ProjectConflict("训练引用记录无法读取，不能安全删除快照或项目") from exc


def _reference_count(database, export_ids):
    export_ids = set(export_ids)
    count = 0
    for task in database.scalars(select(TrainingTask)):
        ids = config_dataset_ids(task.default_multi_dataset_config)
        if task.default_dataset_export_id:
            ids.add(task.default_dataset_export_id)
        count += bool(ids & export_ids)
    for model in database.scalars(select(TrainingModel)):
        ids = config_dataset_ids(model.multi_dataset_config) | snapshot_dataset_ids(
            model.dataset_snapshot
        )
        if model.dataset_export_id:
            ids.add(model.dataset_export_id)
        count += bool(ids & export_ids)
    return count
