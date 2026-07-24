import math
from dataclasses import dataclass
from typing import Literal

SamplingMode = Literal["target_frames", "frame_interval", "time_interval"]


class InvalidSampling(ValueError):
    pass


@dataclass(frozen=True)
class SamplingInput:
    mode: SamplingMode
    parameters: dict[str, int]


@dataclass(frozen=True)
class SamplingEstimate:
    mode: SamplingMode
    parameters: dict[str, int]
    computed_interval: int | None
    expected_frames: int


def calculate_sampling(
    total_frames: int,
    fps: float,
    duration: float,
    value: SamplingInput,
) -> SamplingEstimate:
    if total_frames <= 0 or fps <= 0 or duration <= 0:
        raise InvalidSampling("video media metadata is incomplete")

    if value.mode == "target_frames":
        minimum = value.parameters.get("minimum", 50)
        maximum = value.parameters.get("maximum", 200)
        if not 10 <= minimum <= 100 or not 100 <= maximum <= 300 or minimum >= maximum:
            raise InvalidSampling("target frame range is invalid")
        ratio = min(1.0, max(0.0, (duration - 120) / 480))
        target = min(total_frames, round(minimum + ratio * (maximum - minimum)))
        return SamplingEstimate(
            mode=value.mode,
            parameters={"minimum": minimum, "maximum": maximum},
            computed_interval=None,
            expected_frames=target,
        )

    if value.mode == "frame_interval":
        interval = value.parameters.get("interval", 30)
        if not 1 <= interval <= 100_000:
            raise InvalidSampling("frame interval is invalid")
        return SamplingEstimate(
            mode=value.mode,
            parameters={"interval": interval},
            computed_interval=interval,
            expected_frames=math.ceil(total_frames / interval),
        )

    if value.mode != "time_interval":
        raise InvalidSampling("sampling mode is invalid")
    seconds = value.parameters.get("seconds", 1)
    frames = value.parameters.get("frames", 1)
    if not 1 <= seconds <= 10 or not 1 <= frames <= 10:
        raise InvalidSampling("time interval is invalid")
    interval = max(1, int(fps * seconds / frames))
    return SamplingEstimate(
        mode=value.mode,
        parameters={"seconds": seconds, "frames": frames},
        computed_interval=interval,
        expected_frames=math.ceil(total_frames / interval),
    )


def source_frame_index(
    estimate: SamplingEstimate,
    sequence_zero_based: int,
    total_frames: int,
) -> int:
    if not 0 <= sequence_zero_based < estimate.expected_frames:
        raise ValueError("frame sequence is outside the sampling estimate")
    if estimate.mode == "target_frames":
        return math.ceil(
            sequence_zero_based * total_frames / estimate.expected_frames
        )
    assert estimate.computed_interval is not None
    return sequence_zero_based * estimate.computed_interval


def ffmpeg_select(estimate: SamplingEstimate, total_frames: int) -> str:
    if estimate.mode == "target_frames":
        target = estimate.expected_frames
        return (
            "not(eq("
            f"floor(n*{target}/{total_frames})\\,"
            f"floor((n-1)*{target}/{total_frames})"
            "))"
        )
    assert estimate.computed_interval is not None
    return f"not(mod(n\\,{estimate.computed_interval}))"
