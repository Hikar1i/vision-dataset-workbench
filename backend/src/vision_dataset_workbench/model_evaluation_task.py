import importlib
import json
import os
import shutil
import threading
import unicodedata
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .models import EvaluationDataset, InferenceModel, ModelArtifact, ModelEvaluation, Task
from .services.gpu_leases import GpuLeaseService


class ModelEvaluationDeferred(RuntimeError):
    pass


class ModelEvaluationCanceled(RuntimeError):
    pass


def execute_model_evaluation(
    session_factory: sessionmaker,
    workspace: Path,
    task_id: str,
    task_temp: Path,
    now: Callable[[], datetime],
    heartbeat: Callable[[str, int | None], None],
    canceled: Callable[[str], bool],
    gpu_leases: GpuLeaseService,
) -> None:
    with session_factory() as database:
        task = database.get(Task, task_id)
        if task is None or task.status != "running":
            raise RuntimeError("active model evaluation not found")
        evaluation = database.get(
            ModelEvaluation, str(json.loads(task.payload).get("evaluation_id") or "")
        )
        if evaluation is None:
            raise RuntimeError("model evaluation not found")
        model = database.get(InferenceModel, evaluation.model_id)
        dataset = database.get(EvaluationDataset, evaluation.evaluation_dataset_id)
        if (
            model is None
            or dataset is None
            or not dataset.storage_path
            or dataset.status != "ready"
        ):
            raise RuntimeError("evaluation resources are unavailable")
        if (
            model.sha256 != evaluation.source_model_sha256
            or dataset.content_sha256 != evaluation.dataset_sha256
        ):
            raise RuntimeError("model or evaluation dataset changed after task creation")
        model_path = workspace / str(model.storage_path or "")
        if evaluation.format != "pt":
            artifact = database.scalar(
                select(ModelArtifact).where(
                    ModelArtifact.model_id == model.id,
                    ModelArtifact.format == evaluation.format,
                    ModelArtifact.sha256 == evaluation.artifact_sha256,
                    ModelArtifact.status == "ready",
                    ModelArtifact.deleted_at.is_(None),
                )
            )
            if artifact is None or not artifact.storage_path:
                raise RuntimeError("selected model artifact is unavailable")
            model_path = workspace / artifact.storage_path
        dataset_path = (workspace / dataset.storage_path).resolve(strict=True)
        dataset_classes = json.loads(dataset.classes)
        evaluation.status = "running"
        evaluation.started_at = now()
        database.commit()
    lease = gpu_leases.acquire("evaluation", task_id)
    if lease is None:
        raise ModelEvaluationDeferred("no GPU is currently available")
    stop = threading.Event()

    def keep_alive():
        while not stop.wait(10):
            heartbeat(task_id, None)
            gpu_leases.renew("evaluation", task_id)

    thread = threading.Thread(target=keep_alive, daemon=True, name=f"evaluation-{task_id}")
    thread.start()
    try:
        ultralytics = importlib.import_module("ultralytics")
        runner = ultralytics.YOLO(str(model_path))
        names = runner.names
        model_classes = (
            [str(names[index]) for index in sorted(names)]
            if isinstance(names, dict)
            else [str(item) for item in names]
        )
        model_classes = [unicodedata.normalize("NFC", name.strip()) for name in model_classes]
        if (
            len(set(model_classes)) != len(model_classes)
            or set(model_classes) != set(dataset_classes)
            or len(model_classes) != len(dataset_classes)
        ):
            missing = sorted(set(model_classes) - set(dataset_classes))
            extra = sorted(set(dataset_classes) - set(model_classes))
            raise RuntimeError(f"类别不兼容；缺少 {missing or '无'}，多余 {extra or '无'}")
        mapping = {index: model_classes.index(name) for index, name in enumerate(dataset_classes)}
        prepared = task_temp / "prepared"
        images = prepared / "images"
        labels = prepared / "labels"
        images.mkdir(parents=True)
        labels.mkdir()
        source_images = sorted((dataset_path / "images").iterdir())
        for index, source in enumerate(source_images):
            if canceled(task_id):
                raise ModelEvaluationCanceled("evaluation canceled")
            try:
                os.link(source, images / source.name)
            except OSError:
                shutil.copy2(source, images / source.name)
            label_source = dataset_path / "labels" / f"{source.stem}.txt"
            lines = []
            for line in label_source.read_text("utf-8-sig").splitlines():
                parts = line.split()
                if parts:
                    parts[0] = str(mapping[int(parts[0])])
                lines.append(" ".join(parts))
            (labels / f"{source.stem}.txt").write_text(
                "\n".join(lines) + ("\n" if lines else ""), "utf-8"
            )
            if index % 25 == 0:
                heartbeat(task_id, min(20, round((index + 1) * 20 / len(source_images))))
        data_file = prepared / "data.yaml"
        data_file.write_text(
            json.dumps(
                {
                    "path": str(prepared),
                    "val": "images",
                    "names": {index: name for index, name in enumerate(model_classes)},
                },
                ensure_ascii=False,
            ),
            "utf-8",
        )
        config = json.loads(evaluation.config)
        if canceled(task_id):
            raise ModelEvaluationCanceled("evaluation canceled")
        results = runner.val(
            data=str(data_file),
            conf=config["conf"],
            iou=config["iou"],
            batch=1,
            max_det=config["max_det"],
            device=lease.gpu_index,
            plots=True,
            project=str(task_temp),
            name="results",
            exist_ok=True,
            verbose=False,
        )
        box = results.box
        metrics = {
            "precision": float(box.mp),
            "recall": float(box.mr),
            "map50": float(box.map50),
            "map50_95": float(box.map),
            "preprocess_ms": float(results.speed.get("preprocess", 0)),
            "inference_ms": float(results.speed.get("inference", 0)),
            "postprocess_ms": float(results.speed.get("postprocess", 0)),
        }
        arrays = {
            "precision": list(getattr(box, "p", [])),
            "recall": list(getattr(box, "r", [])),
            "map50": list(getattr(box, "ap50", [])),
            "map50_95": list(getattr(box, "maps", [])),
        }
        per_class = [
            {
                "class_index": index,
                "class_name": name,
                **{
                    key: float(values[index]) if index < len(values) else None
                    for key, values in arrays.items()
                },
            }
            for index, name in enumerate(model_classes)
        ]
        target = (
            workspace
            / "model-projects"
            / evaluation.model_project_id
            / "evaluations"
            / evaluation.id
        )
        target.mkdir(parents=True, exist_ok=True)
        confusion = _copy_plot(
            task_temp / "results",
            target,
            ("confusion_matrix_normalized.png", "confusion_matrix.png"),
            "confusion-matrix.png",
        )
        pr_curve = _copy_plot(
            task_temp / "results", target, ("BoxPR_curve.png", "PR_curve.png"), "pr-curve.png"
        )
        finished = now()
        with session_factory() as database:
            evaluation = database.get(ModelEvaluation, evaluation.id)
            task = database.get(Task, task_id)
            if evaluation is None or task is None:
                raise RuntimeError("evaluation resources disappeared")
            evaluation.class_mapping = json.dumps(mapping)
            evaluation.metrics = json.dumps(metrics)
            evaluation.per_class_metrics = json.dumps(per_class, ensure_ascii=False)
            evaluation.confusion_matrix_path = (
                confusion.relative_to(workspace).as_posix() if confusion else None
            )
            evaluation.pr_curve_path = (
                pr_curve.relative_to(workspace).as_posix() if pr_curve else None
            )
            evaluation.status = "succeeded"
            evaluation.finished_at = finished
            task.status = "succeeded"
            task.progress = 100
            task.result = json.dumps({"evaluation_id": evaluation.id})
            task.finished_at = finished
            task.updated_at = finished
            task.lease_owner = None
            task.lease_expires_at = None
            database.commit()
    finally:
        stop.set()
        thread.join(timeout=1)
        gpu_leases.release("evaluation", task_id)


def _copy_plot(source: Path, target: Path, candidates: tuple[str, ...], name: str):
    for candidate in candidates:
        path = source / candidate
        if path.is_file():
            destination = target / name
            shutil.copy2(path, destination)
            return destination
    return None
