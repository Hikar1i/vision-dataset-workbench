import base64
import json
import math
import mimetypes
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from .inference import Detection


class XAnyLabelingUnavailable(ValueError):
    pass


@dataclass(frozen=True)
class RemoteModelOption:
    key: str
    model_id: str
    task_id: str | None
    name: str
    batch_processing_mode: Literal["default", "text_prompt"]


def normalize_server_url(value: str) -> str:
    raw = value.strip()
    try:
        parsed = urlsplit(raw)
        _ = parsed.port
    except ValueError as exc:
        raise XAnyLabelingUnavailable("server URL is invalid") from exc
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise XAnyLabelingUnavailable("server URL must use http or https")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise XAnyLabelingUnavailable(
            "server URL must not contain credentials, query, or fragment"
        )
    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def _option_key(model_id: str, task_id: str | None) -> str:
    return json.dumps([model_id, task_id], ensure_ascii=False, separators=(",", ":"))


_UNSUPPORTED_TASK_WORDS = {
    "caption",
    "classification",
    "keypoint",
    "point",
    "pointing",
    "polygon",
    "segmentation",
}


def _rectangle_task(task: dict[str, object]) -> bool:
    words = f"{task.get('id', '')} {task.get('name', '')}".lower().replace("_", " ").split()
    return not _UNSUPPORTED_TASK_WORDS.intersection(words)


class XAnyLabelingClient:
    def __init__(
        self,
        server_url: str,
        api_key: str | None = None,
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self.server_url = normalize_server_url(server_url)
        self.api_key = api_key
        self.transport = transport

    def _request(self, method: str, path: str, **kwargs) -> object:
        headers = {"Token": self.api_key} if self.api_key else None
        try:
            with httpx.Client(
                transport=self.transport,
                timeout=httpx.Timeout(120, connect=5),
                headers=headers,
                trust_env=False,
            ) as client:
                response = client.request(method, f"{self.server_url}{path}", **kwargs)
                response.raise_for_status()
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise XAnyLabelingUnavailable("X-AnyLabeling server request failed") from exc
        if not isinstance(payload, dict) or payload.get("success") is not True:
            error = payload.get("error") if isinstance(payload, dict) else None
            message = error.get("message") if isinstance(error, dict) else None
            raise XAnyLabelingUnavailable(
                str(message or "X-AnyLabeling server returned an invalid response")
            )
        return payload.get("data")

    def list_models(self) -> list[RemoteModelOption]:
        data = self._request("GET", "/v1/models")
        if not isinstance(data, dict):
            raise XAnyLabelingUnavailable("X-AnyLabeling model catalog is invalid")
        options: list[RemoteModelOption] = []
        for raw_id, raw_metadata in data.items():
            if not isinstance(raw_id, str) or not isinstance(raw_metadata, dict):
                raise XAnyLabelingUnavailable("X-AnyLabeling model catalog is invalid")
            if raw_metadata.get("capabilities"):
                continue
            model_name = str(raw_metadata.get("display_name") or raw_id)
            tasks = raw_metadata.get("available_tasks")
            if isinstance(tasks, list) and tasks:
                for task in tasks:
                    if not isinstance(task, dict) or not _rectangle_task(task):
                        continue
                    task_id = str(task.get("id") or "").strip()
                    mode = task.get("batch_processing_mode") or raw_metadata.get(
                        "batch_processing_mode"
                    )
                    if not task_id or mode not in {"default", "text_prompt"}:
                        continue
                    task_name = str(task.get("name") or task_id)
                    options.append(
                        RemoteModelOption(
                            _option_key(raw_id, task_id),
                            raw_id,
                            task_id,
                            f"{model_name} / {task_name}",
                            mode,
                        )
                    )
                continue
            mode = raw_metadata.get("batch_processing_mode")
            if mode in {"default", "text_prompt"}:
                options.append(
                    RemoteModelOption(
                        _option_key(raw_id, None), raw_id, None, model_name, mode
                    )
                )
        return options

    def predict(
        self,
        option: RemoteModelOption,
        image_path: Path,
        categories: list[str],
        confidence: float,
        iou: float,
    ) -> list[Detection]:
        mime = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        image = base64.b64encode(image_path.read_bytes()).decode()
        params: dict[str, object] = {
            "conf_threshold": confidence,
            "iou_threshold": iou,
        }
        if option.task_id:
            params["current_task"] = option.task_id
        if option.batch_processing_mode == "text_prompt":
            params["text_prompt"] = ", ".join(categories)
        data = self._request(
            "POST",
            "/v1/predict",
            json={
                "model": option.model_id,
                "image": f"data:{mime};base64,{image}",
                "params": params,
            },
        )
        if not isinstance(data, dict) or not isinstance(data.get("shapes"), list):
            raise XAnyLabelingUnavailable("X-AnyLabeling prediction response is invalid")
        allowed = set(categories)
        detections = [self._detection(shape) for shape in data["shapes"]]
        return [item for item in detections if not allowed or item.label in allowed]

    @staticmethod
    def _detection(shape: object) -> Detection:
        if not isinstance(shape, dict) or shape.get("shape_type") != "rectangle":
            raise XAnyLabelingUnavailable("remote model returned a non-rectangle shape")
        label = str(shape.get("label") or "").strip().lower()
        points = shape.get("points")
        if not label or not isinstance(points, list) or len(points) not in {2, 4}:
            raise XAnyLabelingUnavailable("remote model returned an invalid rectangle")
        try:
            coordinates = [(float(point[0]), float(point[1])) for point in points]
            score = float(shape["score"]) if shape.get("score") is not None else None
        except (IndexError, TypeError, ValueError) as exc:
            raise XAnyLabelingUnavailable("remote model returned an invalid rectangle") from exc
        values = [value for point in coordinates for value in point]
        if score is not None:
            values.append(score)
        if not all(math.isfinite(value) for value in values):
            raise XAnyLabelingUnavailable("remote model returned an invalid rectangle")
        xs, ys = zip(*coordinates, strict=True)
        x_min, x_max, y_min, y_max = min(xs), max(xs), min(ys), max(ys)
        if x_max <= x_min or y_max <= y_min:
            raise XAnyLabelingUnavailable("remote model returned an invalid rectangle")
        return Detection(label, x_min, y_min, x_max, y_max, score)
