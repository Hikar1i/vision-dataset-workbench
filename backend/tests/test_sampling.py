import math

import pytest

from vision_dataset_workbench.sampling import (
    InvalidSampling,
    SamplingInput,
    calculate_sampling,
    ffmpeg_select,
    source_frame_index,
)


def test_target_mode_is_bounded_and_predictable():
    config = SamplingInput("target_frames", {"minimum": 50, "maximum": 200})

    short = calculate_sampling(3600, 30, 120, config)
    middle = calculate_sampling(9000, 30, 300, config)
    long = calculate_sampling(18000, 30, 600, config)
    very_long = calculate_sampling(108000, 30, 3600, config)

    assert [item.expected_frames for item in (short, middle, long, very_long)] == [
        50,
        106,
        200,
        200,
    ]
    assert middle.computed_interval is None
    assert source_frame_index(middle, 0, 9000) == 0
    assert source_frame_index(middle, 105, 9000) == math.ceil(105 * 9000 / 106)
    assert "floor" in ffmpeg_select(middle, 9000)


def test_target_mode_keeps_all_frames_when_source_is_smaller():
    result = calculate_sampling(
        8,
        2,
        4,
        SamplingInput("target_frames", {"minimum": 10, "maximum": 100}),
    )

    assert result.expected_frames == 8
    assert source_frame_index(result, 7, 8) == 7


def test_interval_modes_count_frame_zero():
    fixed = calculate_sampling(
        101,
        25,
        4.04,
        SamplingInput("frame_interval", {"interval": 10}),
    )
    timed = calculate_sampling(
        101,
        25,
        4.04,
        SamplingInput("time_interval", {"seconds": 2, "frames": 5}),
    )

    assert fixed.expected_frames == 11
    assert fixed.computed_interval == 10
    assert timed.expected_frames == 11
    assert timed.computed_interval == 10
    assert source_frame_index(fixed, 10, 101) == 100
    assert "mod" in ffmpeg_select(fixed, 101)


@pytest.mark.parametrize(
    "value",
    [
        SamplingInput("target_frames", {"minimum": 9, "maximum": 200}),
        SamplingInput("target_frames", {"minimum": 50, "maximum": 301}),
        SamplingInput("target_frames", {"minimum": 100, "maximum": 100}),
        SamplingInput("frame_interval", {"interval": 0}),
        SamplingInput("time_interval", {"seconds": 11, "frames": 1}),
    ],
)
def test_invalid_sampling_parameters_are_rejected(value):
    with pytest.raises(InvalidSampling):
        calculate_sampling(1000, 25, 40, value)


def test_incomplete_media_metadata_is_rejected():
    with pytest.raises(InvalidSampling):
        calculate_sampling(
            0,
            25,
            0,
            SamplingInput("target_frames", {"minimum": 50, "maximum": 200}),
        )
