import base64
import json
import mimetypes
import re
from pathlib import Path

import httpx

from ..inference import Detection

PROMPT = (
    "你是目标检测助手。只识别图像中的目标检测矩形框。"
    "请仅输出 JSON 数组，每项包含 label、x_min、y_min、x_max、y_max、confidence；"
    "坐标使用图像像素坐标。允许的类别：{categories}"
)


class LLMAnnotationError(ValueError):
    pass


def predict(
    connection: dict[str, object],
    image_path: Path,
    categories: list[str],
    confidence: float,
) -> list[Detection]:
    image = base64.b64encode(image_path.read_bytes()).decode()
    prompt = PROMPT.format(categories=", ".join(categories) or "不限")
    if connection.get("api_type") == "anthropic":
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mimetypes.guess_type(image_path.name)[0]
                    or "image/jpeg",
                    "data": image,
                },
            },
        ]
    else:
        media_type = mimetypes.guess_type(image_path.name)[0] or "image/jpeg"
        content = [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": f"data:{media_type};base64,{image}"},
            },
        ]
    response_content = _complete(connection, content, max_tokens=2048)
    match = re.search(r"\[[\s\S]*\]", response_content)
    if not match:
        raise LLMAnnotationError("在线模型未返回合法 JSON 数组")
    try:
        values = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise LLMAnnotationError("在线模型返回的 JSON 无法解析") from exc
    detections = []
    allowed = set(categories)
    for item in values:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip().lower()
        score = float(item.get("confidence", 0))
        if not label or score < confidence or (allowed and label not in allowed):
            continue
        try:
            detections.append(Detection(label, float(item["x_min"]), float(item["y_min"]), float(item["x_max"]), float(item["y_max"]), score))
        except (KeyError, TypeError, ValueError):
            continue
    return detections


def probe(connection: dict[str, object]) -> None:
    _complete(connection, "Reply with OK.", max_tokens=8)


def _complete(
    connection: dict[str, object],
    content: str | list[dict[str, object]],
    *,
    max_tokens: int,
) -> str:
    advanced = connection["advanced_options"]
    temperature = advanced.get("temperature", 0.2)
    if connection.get("api_type") == "anthropic":
        endpoint = f"{str(connection['base_url']).rstrip('/')}/messages"
        headers = (
            {"x-api-key": str(connection["api_key"])}
            if connection.get("api_key")
            else {}
        )
        headers["anthropic-version"] = "2023-06-01"
        payload = {
            "model": connection["model_name"],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": content}],
        }
    else:
        endpoint = f"{str(connection['base_url']).rstrip('/')}/chat/completions"
        headers = (
            {"Authorization": f"Bearer {connection['api_key']}"}
            if connection.get("api_key")
            else {}
        )
        payload = {
            "model": connection["model_name"],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": content}],
        }
    timeout = float(advanced.get("inference_timeout_seconds", 120))
    try:
        response = httpx.post(endpoint, headers=headers, json=payload, timeout=timeout)
        response.raise_for_status()
        body = response.json()
        return (
            body["content"][0]["text"]
            if connection.get("api_type") == "anthropic"
            else body["choices"][0]["message"]["content"]
        )
    except Exception as exc:
        raise LLMAnnotationError(f"在线模型请求失败: {exc}") from exc
