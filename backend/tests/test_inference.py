from pathlib import Path
from types import SimpleNamespace

from vision_dataset_workbench.inference import Detection, InferenceRunner


class FakeYoloRunner(InferenceRunner):
    def _predict_yolo(self, *_args):
        return [Detection("helmet", 0, 0, 100, 100, 0.9)]


def test_inference_runner_uses_yolo_path():
    result = FakeYoloRunner().predict(
        SimpleNamespace(id="model-id"),
        Path("model.pt"),
        Path("image.jpg"),
        [],
        0.25,
        0.45,
    )

    assert result == [Detection("helmet", 0, 0, 100, 100, 0.9)]
