import importlib
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .models import InferenceModel


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
    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._lock = threading.RLock()
        self._model_locks: dict[str, threading.Lock] = {}

    def predict(
        self,
        model: InferenceModel,
        model_path: Path,
        image_path: Path,
        categories: list[str],
        confidence: float,
        iou: float,
    ) -> list[Detection]:
        with self._lock:
            model_lock = self._model_locks.setdefault(model.id, threading.Lock())
        with model_lock:
            return self._predict_yolo(
                model, model_path, image_path, categories, confidence, iou
            )

    def _predict_yolo(
        self,
        model: InferenceModel,
        model_path: Path,
        image_path: Path,
        categories: list[str],
        confidence: float,
        iou: float,
    ) -> list[Detection]:
        try:
            ultralytics = importlib.import_module("ultralytics")
            torch = importlib.import_module("torch")
        except ModuleNotFoundError as exc:
            raise InferenceUnavailable("Ultralytics GPU dependencies are not installed") from exc
        if not torch.cuda.is_available():
            raise InferenceUnavailable("PyTorch CUDA runtime is unavailable")
        with self._lock:
            loaded = self._cache.get(model.id)
            if loaded is None:
                loaded = ultralytics.YOLO(str(model_path))
                self._cache[model.id] = loaded
        try:
            result = loaded.predict(
                source=str(image_path),
                conf=confidence,
                iou=iou,
                device=0,
                verbose=False,
            )[0]
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
