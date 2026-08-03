import base64
import json

import httpx
import pytest

from vision_dataset_workbench.xanylabeling import (
    RemoteModelOption,
    XAnyLabelingClient,
    XAnyLabelingUnavailable,
    normalize_server_url,
)


def test_server_url_validation():
    assert normalize_server_url(" http://127.0.0.1:44444/ ") == (
        "http://127.0.0.1:44444"
    )
    for value in (
        "ftp://server.test",
        "http://user:password@server.test",
        "http://server.test?token=value",
        "http://server.test/#fragment",
    ):
        with pytest.raises(XAnyLabelingUnavailable):
            normalize_server_url(value)


def test_catalog_flattens_rectangle_tasks_and_sends_api_key():
    requests = []

    def handler(request: httpx.Request):
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "grounding": {
                        "display_name": "Grounding",
                        "batch_processing_mode": "text_prompt",
                        "capabilities": {},
                    },
                    "locate": {
                        "display_name": "LocateAnything",
                        "batch_processing_mode": "text_prompt",
                        "available_tasks": [
                            {"id": "detection", "name": "Detection"},
                            {"id": "pointing", "name": "Pointing"},
                            {
                                "id": "text_detection",
                                "name": "Text Detection",
                                "batch_processing_mode": "default",
                            },
                        ],
                    },
                    "caption": {"batch_processing_mode": "caption"},
                },
            },
        )

    client = XAnyLabelingClient(
        "http://server.test/", "api-key", transport=httpx.MockTransport(handler)
    )

    options = client.list_models()

    assert [(item.model_id, item.task_id) for item in options] == [
        ("grounding", None),
        ("locate", "detection"),
        ("locate", "text_detection"),
    ]
    assert json.loads(options[1].key) == ["locate", "detection"]
    assert requests[0].headers["Token"] == "api-key"


def test_prediction_maps_data_uri_task_and_rectangles(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"image-data")
    received = {}

    def handler(request: httpx.Request):
        received.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "shapes": [
                        {
                            "label": "helmet",
                            "shape_type": "rectangle",
                            "points": [[10, 20], [110, 20], [110, 220], [10, 220]],
                            "score": 0.91,
                        }
                    ],
                    "description": "",
                },
            },
        )

    client = XAnyLabelingClient(
        "http://server.test", transport=httpx.MockTransport(handler)
    )
    option = RemoteModelOption(
        '["locate","grounding"]',
        "locate",
        "grounding",
        "Locate / Grounding",
        "text_prompt",
    )

    detections = client.predict(option, image, ["helmet"], 0.25, 0.45)

    assert detections[0].label == "helmet"
    assert received["params"] == {
        "conf_threshold": 0.25,
        "iou_threshold": 0.45,
        "current_task": "grounding",
        "text_prompt": "helmet",
    }
    assert base64.b64decode(received["image"].split(",", 1)[1]) == b"image-data"


def test_prediction_rejects_non_rectangle_shapes(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"image")
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "shapes": [
                        {
                            "label": "helmet",
                            "shape_type": "point",
                            "points": [[10, 20]],
                        }
                    ]
                },
            },
        )
    )
    client = XAnyLabelingClient("http://server.test", transport=transport)
    option = RemoteModelOption('["point",null]', "point", None, "Point", "default")

    with pytest.raises(XAnyLabelingUnavailable, match="non-rectangle"):
        client.predict(option, image, [], 0.25, 0.45)


def test_prediction_preserves_missing_confidence(tmp_path):
    image = tmp_path / "frame.jpg"
    image.write_bytes(b"image")
    transport = httpx.MockTransport(
        lambda _request: httpx.Response(
            200,
            json={
                "success": True,
                "data": {
                    "shapes": [
                        {
                            "label": "person",
                            "shape_type": "rectangle",
                            "points": [[1, 2], [10, 20]],
                        }
                    ]
                },
            },
        )
    )
    client = XAnyLabelingClient("http://server.test", transport=transport)
    option = RemoteModelOption('["model",null]', "model", None, "Model", "default")

    detections = client.predict(option, image, [], 0.25, 0.45)

    assert detections[0].confidence is None
