import json
import re


def safe_export_name(value: str, max_length: int = 80) -> str:
    value = value.strip(" .")
    cleaned = "".join(
        character if character.isalnum() or character in " -_" else "_"
        for character in value
    )
    cleaned = re.sub(r"_+", "_", cleaned)
    return cleaned[:max_length].rstrip(" .")


def split_videos(
    frame_counts: dict[str, int], train_ratio: float
) -> tuple[list[str], list[str]]:
    if not 0 <= train_ratio <= 1:
        raise ValueError("train ratio must be between 0 and 1")
    if any(count < 0 for count in frame_counts.values()):
        raise ValueError("frame counts must be non-negative")
    if train_ratio == 0:
        return [], sorted(frame_counts)
    if train_ratio == 1:
        return sorted(frame_counts), []

    target_val = sum(frame_counts.values()) * (1 - train_ratio)
    train = [video_id for video_id, count in frame_counts.items() if count > 1000]
    val: list[str] = []
    val_count = 0
    small_videos = sorted(
        (
            (video_id, count)
            for video_id, count in frame_counts.items()
            if count <= 1000
        ),
        key=lambda item: (-item[1], item[0]),
    )
    for video_id, count in small_videos:
        if abs(target_val - (val_count + count)) < abs(target_val - val_count):
            val.append(video_id)
            val_count += count
        else:
            train.append(video_id)
    return sorted(train), sorted(val)


def yolo_line(
    class_id: int,
    box: tuple[int, int, int, int],
    width: int,
    height: int,
) -> str:
    if width <= 0 or height <= 0:
        raise ValueError("image dimensions must be positive")
    x_min, y_min, x_max, y_max = box
    if class_id < 0 or not (0 <= x_min < x_max <= width and 0 <= y_min < y_max <= height):
        raise ValueError("invalid annotation box")
    center_x = (x_min + x_max) / 2 / width
    center_y = (y_min + y_max) / 2 / height
    box_width = (x_max - x_min) / width
    box_height = (y_max - y_min) / height
    return (
        f"{class_id} {center_x:.6f} {center_y:.6f} "
        f"{box_width:.6f} {box_height:.6f}"
    )


def dataset_yaml(names: list[str]) -> str:
    lines = [
        "path: .",
        "train: train/images",
        "val: val/images",
        f"nc: {len(names)}",
        "names:",
    ]
    lines.extend(
        f"  {index}: {json.dumps(name, ensure_ascii=False)}"
        for index, name in enumerate(names)
    )
    return "\n".join(lines) + "\n"
