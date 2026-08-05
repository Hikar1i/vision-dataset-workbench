import pytest

from vision_dataset_workbench.training.hyperparameters import (
    HyperparameterValidationError,
    catalog_payload,
    parse_raw,
)


def test_catalog_is_unique_and_defaults_are_valid():
    catalog = catalog_payload()
    keys = [item["key"] for item in catalog["items"]]
    assert catalog["version"] == "detect-v1"
    assert len(keys) == len(set(keys))
    assert not {"epochs", "batch", "imgsz", "model", "data"}.intersection(keys)


def test_raw_parser_normalizes_core_and_extra_values():
    parsed = parse_raw("epochs: 200\nbatch: 16\nimgsz: 640\nlr0: 0.01\namp: true\n")
    assert parsed == {
        "epochs": 200,
        "batch_mode": "fixed",
        "batch_value": 16.0,
        "image_size": 640,
        "extra_parameters": {"lr0": 0.01, "amp": True},
    }


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("epochs: 1\nepochs: 2\nbatch: -1\nimgsz: 640", "duplicate_key"),
        ("epochs: 1\nbatch: -1\nimgsz: 640\nunknown: 1", "unknown_key"),
        ("epochs: 1\nbatch: -1\nimgsz: 640\ndevice: 0", "system_key"),
        ("epochs: 1\nbatch: -1\nimgsz: 641", "invalid_value"),
        ("epochs: 1\nbatch: -1\nimgsz: 640\nlr0: [1]", "nested_value"),
        ("epochs: &e 1\nbatch: -1\nimgsz: 640", "yaml_feature"),
    ],
)
def test_raw_parser_strictly_rejects_invalid_input(raw, code):
    with pytest.raises(HyperparameterValidationError) as caught:
        parse_raw(raw)
    assert any(issue.code == code for issue in caught.value.issues)
