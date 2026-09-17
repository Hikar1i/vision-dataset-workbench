import importlib
import json
import subprocess
import threading
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from .inference import InferenceRunner
from .models import InferenceModel, ModelArtifact, ModelInferenceRun, Task
from .services.gpu_leases import GpuLeaseService


class ModelInferenceDeferred(RuntimeError):
    pass


class ModelInferenceCanceled(RuntimeError):
    pass


def execute_video_inference(
    session_factory: sessionmaker,
    workspace: Path,
    task_id: str,
    task_temp: Path,
    now: Callable[[], datetime],
    heartbeat: Callable[[str, int | None], None],
    canceled: Callable[[str], bool],
    gpu_leases: GpuLeaseService,
    runner: InferenceRunner,
) -> None:
    with session_factory() as database:
        task = database.get(Task, task_id)
        if task is None or task.status != "running":
            raise RuntimeError("active video inference task not found")
        run = database.get(ModelInferenceRun, str(json.loads(task.payload).get("run_id") or ""))
        if run is None or run.deleted_at is not None:
            raise ModelInferenceCanceled("inference session removed")
        model = database.get(InferenceModel, run.model_id)
        if model is None or model.sha256 != run.source_model_sha256:
            raise RuntimeError("source model changed after inference was queued")
        source = (workspace / run.source_path).resolve(strict=True)
        model_path = (workspace / str(model.storage_path or "")).resolve()
        if run.format != "pt":
            artifact = database.scalar(
                select(ModelArtifact).where(
                    ModelArtifact.model_id == model.id,
                    ModelArtifact.format == run.format,
                    ModelArtifact.sha256 == run.artifact_sha256,
                    ModelArtifact.status == "ready",
                    ModelArtifact.deleted_at.is_(None),
                )
            )
            if artifact is None or not artifact.storage_path:
                raise RuntimeError("selected model artifact is unavailable")
            model_path = (workspace / artifact.storage_path).resolve()
        parameters = json.loads(run.parameters)
        run.status = "running"
        run.started_at = run.started_at or now()
        database.commit()

    lease = gpu_leases.acquire("inference", task_id)
    if lease is None:
        raise ModelInferenceDeferred("no GPU is currently available")
    stop = threading.Event()

    def keep_alive() -> None:
        while not stop.wait(10):
            heartbeat(task_id, None)
            gpu_leases.renew("inference", task_id)

    thread = threading.Thread(target=keep_alive, name=f"inference-{task_id}", daemon=True)
    thread.start()
    try:
        cv2 = importlib.import_module("cv2")
        capture = cv2.VideoCapture(str(source))
        if not capture.isOpened():
            raise RuntimeError("无法读取上传的视频")
        source_fps = float(capture.get(cv2.CAP_PROP_FPS) or 0)
        width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        total_frames = int(capture.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        if source_fps <= 0 or width <= 0 or height <= 0:
            raise RuntimeError("视频元信息无效")
        stride = int(parameters["stride"])
        preview = source.parent / "source-preview.mp4"
        _transcode(source, preview)
        raw_result = task_temp / "result-raw.mp4"
        writer = cv2.VideoWriter(
            str(raw_result), cv2.VideoWriter_fourcc(*"mp4v"), source_fps / stride, (width, height)
        )
        if not writer.isOpened():
            raise RuntimeError("无法创建检测结果视频")
        frame_file = task_temp / "frame.jpg"
        frame_index = processed = detection_count = 0
        inference_seconds = 0.0
        while True:
            ok, frame = capture.read()
            if not ok:
                break
            if frame_index % stride == 0:
                if canceled(task_id):
                    raise ModelInferenceCanceled("inference canceled")
                cv2.imwrite(str(frame_file), frame)
                started = time.perf_counter()
                detections = runner.predict(
                    model,
                    model_path,
                    frame_file,
                    [],
                    float(parameters["confidence"]),
                    float(parameters["iou"]),
                    model_key=f"{model.id}:{model_path}",
                    device=lease.gpu_index,
                    imgsz=int(parameters["image_size"]),
                    max_det=int(parameters["max_det"]),
                )
                inference_seconds += time.perf_counter() - started
                for item in detections:
                    p1 = (round(item.x_min), round(item.y_min))
                    p2 = (round(item.x_max), round(item.y_max))
                    cv2.rectangle(frame, p1, p2, (182, 160, 39), 2)
                    cv2.putText(frame, f"{item.label} {item.confidence or 0:.2f}", p1, cv2.FONT_HERSHEY_SIMPLEX, 0.55, (182, 160, 39), 2)
                writer.write(frame)
                processed += 1
                detection_count += len(detections)
                if total_frames:
                    heartbeat(task_id, min(95, round(frame_index * 95 / total_frames)))
            frame_index += 1
        capture.release()
        writer.release()
        if processed == 0:
            raise RuntimeError("视频没有可处理帧")
        result = source.parent / "result.mp4"
        _transcode(raw_result, result)
        finished = now()
        with session_factory() as database:
            run = database.get(ModelInferenceRun, run.id)
            task = database.get(Task, task_id)
            if run is None or task is None:
                raise RuntimeError("inference resources disappeared")
            run.status = "succeeded"
            run.result_path = result.relative_to(workspace).as_posix()
            run.statistics = json.dumps(
                {
                    "detections": detection_count,
                    "processed_frames": processed,
                    "source_frames": frame_index,
                    "width": width,
                    "height": height,
                    "inference_seconds": inference_seconds,
                    "inference_fps": processed / inference_seconds if inference_seconds else 0,
                },
                ensure_ascii=False,
            )
            run.finished_at = finished
            task.status = "succeeded"
            task.progress = 100
            task.finished_at = finished
            task.updated_at = finished
            task.lease_owner = None
            task.lease_expires_at = None
            task.result = json.dumps({"run_id": run.id}, ensure_ascii=False)
            database.commit()
    finally:
        stop.set()
        thread.join(timeout=1)
        gpu_leases.release("inference", task_id)


def _transcode(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(source), "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)],
        capture_output=True,
        text=True,
        timeout=3600,
    )
    if result.returncode != 0 or not target.is_file() or target.stat().st_size == 0:
        raise RuntimeError((result.stderr or "视频转码失败")[-2000:])
