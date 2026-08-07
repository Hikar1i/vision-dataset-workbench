import pytest

from vision_dataset_workbench.training.hyperparameters import (
    HyperparameterValidationError,
    catalog_payload,
    parse_raw,
    validate_values,
)


def test_catalog_is_unique_and_defaults_are_valid():
    catalog = catalog_payload()
    keys = [item["key"] for item in catalog["items"]]
    assert catalog["version"] == "detect-v1"
    assert len(keys) == len(set(keys))
    assert not {"epochs", "batch", "imgsz", "model", "data"}.intersection(keys)
    lr0 = next(item for item in catalog["items"] if item["key"] == "lr0")
    patience = next(item for item in catalog["items"] if item["key"] == "patience")
    assert lr0["step"] == 0.001 and lr0["precision"] == 5
    assert patience["maximum"] == 1000 and patience["controls"] is False


def test_raw_parser_normalizes_core_and_extra_values():
    parsed = parse_raw("epochs: 200\nbatch: 16\nimgsz: 640\nlr0: 0.01\namp: true\n")
    assert parsed == {
        "epochs": 200,
        "batch_mode": "fixed",
        "batch_value": 16.0,
        "image_size": 640,
        "extra_parameters": {"lr0": 0.01, "amp": True},
    }


def test_integral_float_batch_is_normalized_as_fixed_batch():
    assert validate_values({"epochs": 5, "batch": 12.0, "imgsz": 640}) == {
        "epochs": 5,
        "batch_mode": "fixed",
        "batch_value": 12.0,
        "image_size": 640,
        "extra_parameters": {},
    }
    with pytest.raises(HyperparameterValidationError):
        validate_values({"epochs": 5, "batch": 12.5, "imgsz": 640})


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("epochs: 1\nepochs: 2\nbatch: -1\nimgsz: 640", "duplicate_key"),
        ("epochs: 1\nbatch: -1\nimgsz: 640\nunknown: 1", "unknown_key"),
        ("epochs: 1\nbatch: -1\nimgsz: 640\ndevice: 0", "system_key"),
        ("epochs: 1\nbatch: -1\nimgsz: 641", "invalid_value"),
        ("epochs: 1\nbatch: -1\nimgsz: 1312", "invalid_value"),
        ("epochs: 1\nbatch: -1\nimgsz: 640\nlr0: [1]", "nested_value"),
        ("epochs: &e 1\nbatch: -1\nimgsz: 640", "yaml_feature"),
    ],
)
def test_raw_parser_strictly_rejects_invalid_input(raw, code):
    with pytest.raises(HyperparameterValidationError) as caught:
        parse_raw(raw)
    assert any(issue.code == code for issue in caught.value.issues)
