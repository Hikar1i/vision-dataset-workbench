"""Directory discovery and YOLO Detect validation; no database or source writes."""

import hashlib
import json
import math
import os
import warnings as python_warnings
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

import yaml
from PIL import Image

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def file_digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def fingerprint(value: object) -> str:
    return hashlib.sha256(
        json.dumps(
            value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode("utf-8")
    ).hexdigest()


def parse_detect_line(raw: str, source_ids: set[int], width: int, height: int):
    if width <= 0 or height <= 0:
        raise ValueError("图片尺寸必须大于零")
    parts = raw.split()
    if len(parts) != 5:
        raise ValueError("必须为五列 YOLO 矩形框，不支持分割、Pose 或 OBB")
    try:
        class_id = int(parts[0])
        cx, cy, w, h = map(float, parts[1:])
    except ValueError as exc:
        raise ValueError("类别编号或坐标无效") from exc
    if class_id < 0 or class_id not in source_ids:
        raise ValueError(f"类别编号 {class_id} 未在来源类别中声明")
    if not all(math.isfinite(v) for v in (cx, cy, w, h)):
        raise ValueError("坐标必须为有限数值")
    if not (0 <= cx <= 1 and 0 <= cy <= 1 and 0 < w <= 1 and 0 < h <= 1):
        raise ValueError("归一化坐标越界")
    left, top, right, bottom = cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2
    if left < -1e-6 or top < -1e-6 or right > 1 + 1e-6 or bottom > 1 + 1e-6:
        raise ValueError("矩形边界越界")
    bounds = [
        max(0.0, left) * width,
        max(0.0, top) * height,
        min(1.0, right) * width,
        min(1.0, bottom) * height,
    ]
    if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
        raise ValueError("矩形面积必须大于零")
    return {
        "source_id": class_id,
        "x_min": bounds[0],
        "y_min": bounds[1],
        "x_max": bounds[2],
        "y_max": bounds[3],
    }


def readable_names(paths: list[str], root_name: str, used: set[str]) -> dict[str, str]:
    leaves = Counter(Path(path).name if path != "." else root_name for path in paths)
    result = {}
    used = {name.casefold() for name in used}
    for path in paths:
        leaf = Path(path).name if path != "." else root_name
        base = leaf if leaves[leaf] == 1 else path.replace("\\", "_").replace("/", "_")
        base = base[:480] or root_name[:480]
        name, suffix = base, 2
        while name.casefold() in used:
            name, suffix = f"{base}_{suffix}", suffix + 1
        result[path] = name
        used.add(name.casefold())
    return result


@dataclass
class ImageScan:
    root: Path
    format: str
    classes: dict[int, str]
    images: list[dict]
    directories: list[dict]
    warnings: list[dict]
    errors: list[dict]
    fingerprint: str
    ignored_files: int

    def preview(self) -> dict:
        return {
            "format": self.format,
            "root_name": self.root.name,
            "fingerprint": self.fingerprint,
            "directories": self.directories,
            "source_classes": [
                {"source_id": key, "name": value} for key, value in sorted(self.classes.items())
            ],
            "total_images": len(self.images),
            "ignored_files": self.ignored_files,
            "annotation_count": sum(len(item["annotations"]) for item in self.images),
            "warnings": self.warnings,
            "errors": self.errors,
        }


def _inside(root: Path, path: Path) -> Path:
    if (
        not path.is_relative_to(root)
        or any(
            parent.is_symlink() for parent in (path, *path.parents) if parent.is_relative_to(root)
        )
        or not path.resolve().is_relative_to(root)
    ):
        raise ValueError("路径或符号链接越出所选数据集根目录")
    return path


def _directory_path(root: Path, raw: str, configured_base: str | None) -> Path:
    if not isinstance(raw, str) or (
        configured_base is not None and not isinstance(configured_base, str)
    ):
        raise ValueError("YAML 路径必须为字符串")
    raw = raw.replace("\\", "/")
    value = Path(raw)
    candidates = []
    if not value.is_absolute():
        if value.parts and value.parts[0] == "..":
            if ".." in value.parts[1:]:
                raise ValueError("目录路径不允许多层父目录跳转")
            candidates.append(root.joinpath(*value.parts[1:]))
        else:
            if ".." in value.parts:
                raise ValueError("目录路径不允许父目录跳转")
            candidates.append(root / value)
            if configured_base and not Path(configured_base).is_absolute():
                candidates.append(root / configured_base / value)
    elif value.is_relative_to(root):
        candidates.append(value)
    if configured_base and value.is_absolute():
        base = Path(configured_base.replace("\\", "/"))
        if base.is_absolute() and value.is_relative_to(base):
            candidates.append(root / value.relative_to(base))
    valid = set()
    for path in candidates:
        try:
            _inside(root, path)
        except ValueError:
            continue
        if path.is_dir():
            valid.add(path.resolve())
    if len(valid) != 1:
        raise ValueError("YAML 声明的图像目录缺失、不安全或存在歧义")
    return valid.pop()


def _configuration(root: Path) -> tuple[dict, dict[int, str], list[Path]]:
    files = [path for path in root.iterdir() if path.suffix.casefold() in {".yaml", ".yml"}]
    preferred = [path for path in files if path.stem in {"data", "dataset"}]
    files = preferred or files
    if len(files) > 1:
        raise ValueError("根目录含多个数据集 YAML，请仅保留一个明确的数据集配置")
    classes = {}
    if files:
        config_path = _inside(root, files[0])
        try:
            config = yaml.safe_load(config_path.read_text("utf-8-sig"))
        except yaml.YAMLError as exc:
            raise ValueError("数据集 YAML 格式错误") from exc
        if not isinstance(config, dict):
            raise ValueError("数据集 YAML 必须是对象")
        names = config.get("names")
        if isinstance(names, list):
            classes = dict(enumerate(names))
        elif isinstance(names, dict):
            try:
                if any(
                    type(key) is not int
                    and not (isinstance(key, str) and key.isascii() and key.isdigit())
                    for key in names
                ):
                    raise ValueError("类别编号必须是整数")
                classes = {int(key): value for key, value in names.items()}
            except (TypeError, ValueError) as exc:
                raise ValueError("names 字典必须以类别整数编号为键") from exc
            if len(classes) != len(names):
                raise ValueError("names 包含重复类别编号")
        else:
            raise ValueError("数据集 YAML 缺少 names 类别列表")
        if not classes or any(
            key < 0 or not isinstance(value, str) or not value.strip()
            for key, value in classes.items()
        ):
            raise ValueError("来源类别编号或名称无效")
        if "nc" in config and (type(config["nc"]) is not int or config["nc"] != len(classes)):
            raise ValueError("nc 与 names 的类别数量不一致")
        directories = []
        for key in ("train", "val", "test"):
            values = config.get(key)
            if values is None or values == "":
                continue
            values = [values] if isinstance(values, str) else values
            if not isinstance(values, list) or any(not isinstance(value, str) for value in values):
                raise ValueError(f"{key} 必须是目录路径或目录列表")
            directories.extend(_directory_path(root, value, config.get("path")) for value in values)
        if not directories:
            raise ValueError("YAML 没有声明图像目录，不支持图片清单 TXT")
        return {"sha256": file_digest(config_path)}, classes, sorted(set(directories))
    classes_file = root / "classes.txt"
    if classes_file.is_file():
        classes = dict(enumerate(_inside(root, classes_file).read_text("utf-8-sig").splitlines()))
        if not classes or any(not name.strip() for name in classes.values()):
            raise ValueError("classes.txt 含空类别名称")
    directories = []
    if (root / "images").is_dir():
        directories.append(_inside(root, root / "images"))
    else:
        directories = [
            _inside(root, path / "images")
            for path in root.iterdir()
            if path.is_dir() and not path.is_symlink() and (path / "images").is_dir()
        ]
    if not directories:
        raise ValueError("没有找到 YOLO 的 images 目录")
    return (
        ({"classes_sha256": file_digest(classes_file)} if classes_file.is_file() else {}),
        classes,
        sorted(directories),
    )


def _image_files(root: Path, directories: list[Path], workspace: Path | None):
    seen = set()
    for directory in directories:
        for parent, children, files in os.walk(directory, followlinks=False):
            parent = Path(parent)
            children[:] = sorted(name for name in children if not name.startswith("."))
            for name in list(children):
                path = _inside(root, parent / name)
                if path.is_symlink() or (workspace and path.resolve().is_relative_to(workspace)):
                    raise ValueError("图像根中包含符号链接或受管工作区")
            for name in sorted(files):
                path = parent / name
                if path.suffix.casefold() not in IMAGE_EXTENSIONS:
                    continue
                _inside(root, path)
                if path.is_symlink():
                    raise ValueError("不支持通过符号链接导入图像")
                relative = path.relative_to(root).as_posix()
                if relative not in seen:
                    seen.add(relative)
                    yield path


def _label_path(root: Path, path: Path) -> Path:
    parts = list(path.relative_to(root).parts)
    indexes = [index for index, part in enumerate(parts[:-1]) if part == "images"]
    if not indexes:
        raise ValueError("图像路径中没有可配对的 images 目录")
    parts[indexes[-1]] = "labels"
    return root.joinpath(*parts).with_suffix(".txt")


def scan_images(
    root: Path,
    format: str | None = None,
    *,
    ignore_annotations: bool = False,
    used_names: set[str] | None = None,
    workspace: Path | None = None,
    heartbeat=None,
) -> ImageScan:
    root = root.resolve()
    if not root.is_dir() or format not in {None, "auto", "images", "yolo_detect"}:
        raise ValueError("请选择纯图像或 YOLO Detect 数据集目录")
    if workspace and root.is_relative_to(workspace.resolve()):
        raise ValueError("受管工作区不能作为导入来源")
    if ignore_annotations:
        format = "images"
    elif format in {None, "auto"}:
        format = "images"
        for parent, children, files in os.walk(root, followlinks=False):
            children[:] = sorted(name for name in children if not name.startswith("."))
            if "labels" in children or (
                Path(parent) == root
                and any(
                    name == "classes.txt" or Path(name).suffix.casefold() in {".yaml", ".yml"}
                    for name in files
                )
            ):
                format = "yolo_detect"
                break
    classes, warnings, errors, records, hashes = {}, [], [], [], {}
    directories = [root]
    config = {}
    if format == "yolo_detect":
        config, classes, directories = _configuration(root)
    files = sorted(_image_files(root, directories, workspace))
    if not files:
        raise ValueError("所选目录没有支持的图像")
    paired_labels = set()
    unknown_ids = set()
    for index, path in enumerate(files):
        if heartbeat:
            heartbeat(index, len(files))
        relative = path.relative_to(root).as_posix()
        try:
            with python_warnings.catch_warnings():
                python_warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(path) as probe:
                    probe.verify()
            with Image.open(path) as image:
                if image.format not in {"JPEG", "PNG", "WEBP", "BMP"}:
                    raise ValueError("图片编码不受支持")
                if image.getexif().get(274, 1) != 1 or getattr(image, "n_frames", 1) != 1:
                    raise ValueError("请先统一图片 EXIF 方向；不支持动态或多页图像")
                width, height = image.size
            with Image.open(path) as image:
                image.load()
            digest = file_digest(path)
            label_digest, annotations, status = None, [], "pending"
            if format == "yolo_detect":
                label_path = _label_path(root, path)
                if label_path.is_file():
                    _inside(root, label_path)
                    paired_labels.add(label_path)
                    text = label_path.read_text("utf-8-sig")
                    label_digest = file_digest(label_path)
                    status = "labeled"
                    for line_number, line in enumerate(text.splitlines(), 1):
                        if not line.strip():
                            continue
                        try:
                            ids = set(classes)
                            if not classes:
                                raw_id = int(line.split()[0])
                                ids.add(raw_id)
                                unknown_ids.add(raw_id)
                            annotations.append(parse_detect_line(line, ids, width, height))
                        except (ValueError, IndexError) as exc:
                            raise ValueError(
                                f"{label_path.relative_to(root).as_posix()}:{line_number}: {exc}"
                            ) from exc
                else:
                    warnings.append(
                        {
                            "code": "missing_label",
                            "path": relative,
                            "message": "缺少 TXT，导入后为待标注",
                        }
                    )
            if digest in hashes:
                warnings.append(
                    {
                        "code": "duplicate",
                        "path": relative,
                        "message": f"与 {hashes[digest]} 内容完全相同",
                    }
                )
            hashes[digest] = relative
            records.append(
                {
                    "path": relative,
                    "directory": path.parent.relative_to(root).as_posix(),
                    "sha256": digest,
                    "width": width,
                    "height": height,
                    "size": path.stat().st_size,
                    "label_digest": label_digest,
                    "annotation_status": status,
                    "annotations": annotations,
                }
            )
        except (
            OSError,
            ValueError,
            Image.DecompressionBombError,
            Image.DecompressionBombWarning,
        ) as exc:
            errors.append({"path": relative, "message": str(exc).replace(str(root), ".")})
    if not classes and unknown_ids:
        classes = {key: "" for key in sorted(unknown_ids)}
        warnings.append(
            {
                "code": "missing_classes",
                "path": ".",
                "message": "缺少类别清单，请明确映射各来源编号",
            }
        )
    if format == "yolo_detect":
        for parent, children, files_in_dir in os.walk(root, followlinks=False):
            children[:] = sorted(
                n for n in children if not n.startswith(".") and not (Path(parent) / n).is_symlink()
            )
            for name in sorted(files_in_dir):
                label = Path(parent) / name
                if (
                    label.suffix.casefold() == ".txt"
                    and "labels" in label.relative_to(root).parts
                    and label not in paired_labels
                ):
                    _inside(root, label)
                    warnings.append(
                        {
                            "code": "orphan_label",
                            "path": label.relative_to(root).as_posix(),
                            "message": "没有对应图片，忽略该 TXT",
                        }
                    )
    ignored_files = 0
    for parent, children, attachments in os.walk(root, followlinks=False):
        children[:] = [
            name
            for name in children
            if not name.startswith(".")
            and not (Path(parent) / name).is_symlink()
            and not (
                workspace and (Path(parent) / name).resolve().is_relative_to(workspace.resolve())
            )
        ]
        for name in attachments:
            path = Path(parent) / name
            if not path.is_symlink() and path.suffix.casefold() not in IMAGE_EXTENSIONS | {
                ".txt",
                ".yaml",
                ".yml",
            }:
                ignored_files += 1
    groups = defaultdict(list)
    for record in records:
        groups[record["directory"]].append(record)
    names = readable_names(sorted(groups), root.name, used_names or set())
    directory_info = [
        {
            "source_relative_path": path,
            "name": names[path],
            "total_images": len(items),
            "labeled_images": sum(item["annotation_status"] == "labeled" for item in items),
            "annotation_count": sum(len(item["annotations"]) for item in items),
        }
        for path, items in sorted(groups.items())
    ]
    source_fingerprint = fingerprint(
        {
            "format": format,
            "classes": classes,
            "config": config,
            "images": records,
            "directories": directory_info,
            "errors": errors,
            "warnings": warnings,
            "ignored_files": ignored_files,
        }
    )
    assert sum(d["total_images"] for d in directory_info) == len(records)
    return ImageScan(
        root,
        format,
        classes,
        records,
        directory_info,
        warnings,
        errors,
        source_fingerprint,
        ignored_files,
    )
