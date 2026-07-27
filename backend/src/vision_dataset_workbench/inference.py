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
    confidence: float


def _intersection_over_union(left: Detection, right: Detection) -> float:
    width = max(0.0, min(left.x_max, right.x_max) - max(left.x_min, right.x_min))
    height = max(0.0, min(left.y_max, right.y_max) - max(left.y_min, right.y_min))
    intersection = width * height
    left_area = (left.x_max - left.x_min) * (left.y_max - left.y_min)
    right_area = (right.x_max - right.x_min) * (right.y_max - right.y_min)
    union = left_area + right_area - intersection
    return intersection / union if union > 0 else 0


def non_maximum_suppression(items: list[Detection], threshold: float) -> list[Detection]:
    kept: list[Detection] = []
    for label in dict.fromkeys(item.label for item in items):
        candidates = sorted(
            (item for item in items if item.label == label),
            key=lambda item: item.confidence,
            reverse=True,
        )
        while candidates:
            best = candidates.pop(0)
            kept.append(best)
            candidates = [
                item
                for item in candidates
                if _intersection_over_union(best, item) <= threshold
            ]
    return kept


class InferenceRunner:
    def __init__(self):
        self._cache: dict[str, Any] = {}
        self._lock = threading.RLock()

    def predict(
        self,
        model: InferenceModel,
        model_path: Path,
        image_path: Path,
        categories: list[str],
        confidence: float,
        iou: float,
    ) -> list[Detection]:
        if model.kind == "yolo":
            return self._predict_yolo(
                model, model_path, image_path, categories, confidence, iou
            )
        if model.kind == "grounding_dino":
            return self._predict_grounding_dino(
                model, model_path, image_path, categories, confidence, iou
            )
        raise InferenceUnavailable("unsupported inference model kind")

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

    def _predict_grounding_dino(
        self,
        model: InferenceModel,
        model_path: Path,
        image_path: Path,
        categories: list[str],
        confidence: float,
        iou: float,
    ) -> list[Detection]:
        if not categories:
            raise InferenceUnavailable("GroundingDINO requires at least one English category")
        try:
            torch = importlib.import_module("torch")
            transformers = importlib.import_module("transformers")
            image_module = importlib.import_module("PIL.Image")
        except ModuleNotFoundError as exc:
            raise InferenceUnavailable("GroundingDINO GPU dependencies are not installed") from exc
        if not torch.cuda.is_available():
            raise InferenceUnavailable("PyTorch CUDA runtime is unavailable")
        with self._lock:
            loaded = self._cache.get(model.id)
            if loaded is None:
                processor = transformers.AutoProcessor.from_pretrained(
                    model_path, local_files_only=True
                )
                detector = transformers.AutoModelForZeroShotObjectDetection.from_pretrained(
                    model_path, local_files_only=True
                ).to("cuda")
                detector.eval()
                loaded = (processor, detector)
                self._cache[model.id] = loaded
        processor, detector = loaded
        try:
            with image_module.open(image_path) as image:
                rgb = image.convert("RGB")
                prompt = ". ".join(categories) + "."
                inputs = processor(images=rgb, text=prompt, return_tensors="pt").to("cuda")
                with torch.no_grad():
                    outputs = detector(**inputs)
                result = processor.post_process_grounded_object_detection(
                    outputs,
                    inputs.input_ids,
                    threshold=confidence,
                    text_threshold=confidence,
                    target_sizes=[rgb.size[::-1]],
                )[0]
            labels = result.get("text_labels")
            if labels is None:
                raise InferenceUnavailable(
                    "GroundingDINO processor did not return text labels"
                )
            detections = [
                Detection(
                    str(label).strip().lower(),
                    *map(float, bounds.tolist()),
                    float(score.item()),
                )
                for bounds, score, label in zip(
                    result["boxes"], result["scores"], labels, strict=True
                )
            ]
            return non_maximum_suppression(detections, iou)
        except InferenceUnavailable:
            raise
        except Exception as exc:
            raise InferenceUnavailable(f"GroundingDINO inference failed: {exc}") from exc
