import json

import httpx

from vision_dataset_workbench.services.llm_annotation import predict, probe


def connection(api_type: str) -> dict[str, object]:
    return {
        "base_url": "http://model.test/v1",
        "api_type": api_type,
        "model_name": "vision-model",
        "api_key": "secret",
        "advanced_options": {"temperature": 0.2, "inference_timeout_seconds": 10},
    }


def test_openai_and_anthropic_use_their_native_payloads(monkeypatch, tmp_path):
    requests: list[httpx.Request] = []

    def post(url, *, headers, json, timeout):
        request = httpx.Request("POST", url, headers=headers, json=json)
        requests.append(request)
        body = (
            {"content": [{"text": '[{"label":"dog","x_min":1,"y_min":2,"x_max":3,"y_max":4,"confidence":0.9}]'}]}
            if url.endswith("/messages")
            else {"choices": [{"message": {"content": '[{"label":"dog","x_min":1,"y_min":2,"x_max":3,"y_max":4,"confidence":0.9}]'}}]}
        )
        return httpx.Response(200, json=body, request=request)

    monkeypatch.setattr(httpx, "post", post)
    image = tmp_path / "frame.png"
    image.write_bytes(b"image")

    assert predict(connection("openai"), image, ["dog"], 0.25)[0].label == "dog"
    assert predict(connection("anthropic"), image, ["dog"], 0.25)[0].label == "dog"
    probe(connection("openai"))
    probe(connection("anthropic"))

    openai_payload = json.loads(requests[0].content)
    anthropic_payload = json.loads(requests[1].content)
    assert requests[0].url.path.endswith("/chat/completions")
    assert requests[0].headers["authorization"] == "Bearer secret"
    assert openai_payload["messages"][0]["content"][1]["type"] == "image_url"
    assert requests[1].url.path.endswith("/messages")
    assert requests[1].headers["x-api-key"] == "secret"
    assert anthropic_payload["messages"][0]["content"][1]["type"] == "image"
    assert anthropic_payload["messages"][0]["content"][1]["source"]["media_type"] == "image/png"
