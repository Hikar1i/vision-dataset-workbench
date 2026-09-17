import hashlib
import importlib
import json
import os
import shutil
import threading
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import sessionmaker

from .models import InferenceModel, ModelArtifact, Task
from .services.gpu_leases import GpuLeaseService
from .services.model_artifacts import default_runtime_fingerprint


class ModelConversionDeferred(RuntimeError):
    pass


def execute_model_conversion(
    session_factory: sessionmaker,
    workspace: Path,
    task_id: str,
    task_temp: Path,
    now: Callable[[], datetime],
    heartbeat: Callable[[str, int | None], None],
    gpu_leases: GpuLeaseService,
) -> None:
    with session_factory() as database:
        task = database.get(Task, task_id)
        if task is None or task.status != "running":
            raise RuntimeError("active model conversion task not found")
        payload = json.loads(task.payload)
        artifact = database.get(ModelArtifact, str(payload.get("artifact_id") or ""))
        model = database.get(InferenceModel, str(payload.get("model_id") or ""))
        if artifact is None or artifact.deleted_at is not None or model is None:
            raise RuntimeError("model conversion resources not found")
        if model.deleted_at is not None or model.status != "ready" or not model.storage_path:
            raise RuntimeError("source model is not ready")
        if model.sha256 != payload.get("source_model_sha256"):
            raise RuntimeError("source model changed after conversion was queued")
        source = (workspace / model.storage_path).resolve(strict=True)
        source_root = (workspace / "models" / model.id).resolve()
        if not source.is_file() or not source.is_relative_to(source_root):
            raise RuntimeError("source model file not found")
        config = json.loads(artifact.export_config)
        artifact_format = artifact.format
        artifact.status = "converting"
        artifact.error = None
        artifact.updated_at = now()
        database.commit()

    lease = None
    if artifact_format == "engine":
        lease = gpu_leases.acquire("conversion", task_id)
        if lease is None:
            raise ModelConversionDeferred("no GPU is currently available")
    stop = threading.Event()

    def keep_alive() -> None:
        while not stop.wait(10):
            heartbeat(task_id, None)
            if lease is not None:
                gpu_leases.renew("conversion", task_id)

    thread = threading.Thread(target=keep_alive, name=f"conversion-{task_id}", daemon=True)
    thread.start()
    try:
        staged_source = task_temp / "source.pt"
        try:
            os.link(source, staged_source)
        except OSError:
            shutil.copy2(source, staged_source)
        os.environ.setdefault("YOLO_AUTOINSTALL", "false")
        ultralytics = importlib.import_module("ultralytics")
        model_runner = ultralytics.YOLO(str(staged_source))
        arguments = {
            "format": artifact_format,
            "imgsz": int(config["imgsz"]),
            "batch": 1,
            "dynamic": bool(config["dynamic"]),
            "nms": False,
            "device": "cpu" if lease is None else lease.gpu_index,
        }
        if artifact_format == "onnx":
            arguments["simplify"] = True
        else:
            arguments["half"] = config.get("precision") == "fp16"
        heartbeat(task_id, 10)
        exported = Path(str(model_runner.export(**arguments))).resolve(strict=True)
        suffix = ".onnx" if artifact_format == "onnx" else ".engine"
        if exported.suffix.lower() != suffix or exported.stat().st_size == 0:
            raise RuntimeError("model export produced an invalid file")
        _validate_export(exported, artifact_format)
        with exported.open("rb") as exported_file:
            digest = hashlib.file_digest(exported_file, "sha256").hexdigest()
        target = workspace / "models" / model.id / "artifacts" / f"model{suffix}"
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(exported, target)
        fingerprint = default_runtime_fingerprint()
        if lease is not None:
            device = gpu_leases.device(lease.gpu_uuid)
            fingerprint.update(
                {
                    "gpu_uuid": lease.gpu_uuid,
                    "compute_capability": device.compute_capability if device else "",
                }
            )
        finished = now()
        with session_factory() as database:
            artifact = database.get(ModelArtifact, artifact.id)
            task = database.get(Task, task_id)
            if artifact is None or task is None:
                raise RuntimeError("model conversion resources disappeared")
            artifact.status = "ready"
            artifact.storage_path = target.relative_to(workspace).as_posix()
            artifact.file_size = target.stat().st_size
            artifact.sha256 = digest
            artifact.environment_fingerprint = (
                json.dumps(fingerprint, ensure_ascii=False) if fingerprint else None
            )
            artifact.gpu_uuid = lease.gpu_uuid if lease else None
            artifact.gpu_index = lease.gpu_index if lease else None
            artifact.error = None
            artifact.updated_at = finished
            artifact.completed_at = finished
            task.status = "succeeded"
            task.progress = 100
            task.result = json.dumps(
                {"outcome": "converted", "artifact_id": artifact.id}, ensure_ascii=False
            )
            task.error = None
            task.finished_at = finished
            task.updated_at = finished
            task.lease_owner = None
            task.lease_expires_at = None
            database.commit()
    finally:
        stop.set()
        thread.join(timeout=1)
        if lease is not None:
            gpu_leases.release("conversion", task_id)


def _validate_export(path: Path, artifact_format: str) -> None:
    if artifact_format == "onnx":
        onnx = importlib.import_module("onnx")
        onnx.checker.check_model(onnx.load(str(path)))
        return
    tensorrt = importlib.import_module("tensorrt")
    logger = tensorrt.Logger(tensorrt.Logger.ERROR)
    with tensorrt.Runtime(logger) as runtime:
        if runtime.deserialize_cuda_engine(path.read_bytes()) is None:
            raise RuntimeError("TensorRT engine validation failed")
