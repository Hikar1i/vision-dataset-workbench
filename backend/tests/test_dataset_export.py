import pytest

from vision_dataset_workbench.dataset_export import (
    dataset_yaml,
    safe_export_name,
    split_videos,
    yolo_line,
)


def test_safe_export_name_keeps_readable_characters_and_replaces_unsafe_ones():
    assert safe_export_name(" 火灾/烟雾:V1. ") == "火灾_烟雾_V1"
    assert safe_export_name("a" * 100) == "a" * 80
    assert safe_export_name("///") == "_"


def test_split_videos_honors_extreme_ratios_and_large_video_rule():
    counts = {"large": 1001, "small-a": 200, "small-b": 100}

    assert split_videos(counts, 0) == ([], ["large", "small-a", "small-b"])
    assert split_videos(counts, 1) == (["large", "small-a", "small-b"], [])

    train, val = split_videos(counts, 0.5)
    assert "large" in train
    assert "large" not in val
    assert sum(counts[item] for item in val) == 300
    assert split_videos(counts, 0.5) == (train, val)


def test_split_videos_rejects_invalid_ratio_and_empty_input():
    assert split_videos({}, 0.8) == ([], [])
    with pytest.raises(ValueError, match="train ratio"):
        split_videos({"video": 10}, 1.1)


def test_yolo_line_normalizes_pixel_coordinates():
    assert yolo_line(3, (10, 20, 110, 220), 200, 400) == (
        "3 0.300000 0.300000 0.500000 0.500000"
    )
    with pytest.raises(ValueError, match="image dimensions"):
        yolo_line(0, (0, 0, 1, 1), 0, 10)


def test_dataset_yaml_preserves_sparse_mapping_slots():
    assert dataset_yaml(["person", "cat", "dog", "car"]) == (
        "path: .\n"
        "train: train/images\n"
        "val: val/images\n"
        "nc: 4\n"
        "names:\n"
        '  0: "person"\n'
        '  1: "cat"\n'
        '  2: "dog"\n'
        '  3: "car"\n'
    )
