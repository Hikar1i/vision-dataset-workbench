import importlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import InferenceModel
from .services.gpu_leases import GpuLeaseService


class InferenceUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class Detection:
    label: str
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    confidence: float | None


class InferenceRunner:
    def __init__(self, gpu_leases: GpuLeaseService | None = None):
        self._cache: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._model_locks: dict[str, threading.Lock] = {}
        self._gpu_leases = gpu_leases

    def predict(
        self,
        model: InferenceModel,
        model_path: Path,
        image_path: Path,
        categories: list[str],
        confidence: float,
        iou: float,
        *,
        model_key: str | None = None,
        device: int | None = None,
        imgsz: int | None = None,
        max_det: int = 300,
    ) -> list[Detection]:
        with self._lock:
            model_lock = self._model_locks.setdefault(model.id, threading.Lock())
        with model_lock:
            owner_id = str(uuid4())
            lease = None
            if device is None and self._gpu_leases is not None:
                lease = self._gpu_leases.acquire("inference", owner_id)
                if lease is None:
                    raise InferenceUnavailable("GPU 正忙，请稍后重试")
                device = lease.gpu_index
            try:
                return self._predict_yolo(
                    model,
                    model_path,
                    image_path,
                    categories,
                    confidence,
                    iou,
                    model_key or model.id,
                    0 if device is None else device,
                    imgsz,
                    max_det,
                )
            finally:
                if lease is not None:
                    self._gpu_leases.release("inference", owner_id)

    def _predict_yolo(
        self,
        model: InferenceModel,
        model_path: Path,
        image_path: Path,
        categories: list[str],
        confidence: float,
        iou: float,
        model_key: str,
        device: int,
        imgsz: int | None,
        max_det: int,
    ) -> list[Detection]:
        try:
            ultralytics = importlib.import_module("ultralytics")
            torch = importlib.import_module("torch")
        except ModuleNotFoundError as exc:
            raise InferenceUnavailable("Ultralytics GPU dependencies are not installed") from exc
        if not torch.cuda.is_available():
            raise InferenceUnavailable("PyTorch CUDA runtime is unavailable")
        with self._lock:
            loaded = self._cache.get(model_key)
            if loaded is None:
                loaded = ultralytics.YOLO(str(model_path))
                self._cache[model_key] = loaded
        try:
            arguments = dict(
                source=str(image_path),
                conf=confidence,
                iou=iou,
                device=device,
                max_det=max_det,
                verbose=False,
            )
            if imgsz is not None:
                arguments["imgsz"] = imgsz
            result = loaded.predict(**arguments)[0]
            names = result.names
            allowed = set(categories)
            detections = []
            for bounds, score, class_id in zip(
                result.boxes.xyxy.cpu().tolist(),
                result.boxes.conf.cpu().tolist(),
                result.boxes.cls.cpu().tolist(),
                strict=True,
            ):
                label = str(names[int(class_id)]).strip().lower()
                if allowed and label not in allowed:
                    continue
                detections.append(
                    Detection(label, *map(float, bounds), float(score))
                )
            return detections
        except InferenceUnavailable:
            raise
        except Exception as exc:
            raise InferenceUnavailable(f"YOLO inference failed: {exc}") from exc
