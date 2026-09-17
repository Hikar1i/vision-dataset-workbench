import hashlib
import json
import math
import os
import shutil
import stat
import unicodedata
import zipfile
from collections.abc import Callable
from datetime import datetime
from pathlib import Path, PurePosixPath

from PIL import Image
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from .models import EvaluationDataset, Task

MAX_EXPANDED_BYTES = 5 * 1024 * 1024 * 1024
MAX_ENTRIES = 10_500
MAX_IMAGES = 5_000
MAX_IMAGE_BYTES = 50 * 1024 * 1024
MAX_LABEL_BYTES = 5 * 1024 * 1024


class EvaluationDatasetCanceled(RuntimeError):
    pass


def execute_evaluation_dataset_import(
    session_factory: sessionmaker,
    workspace: Path,
    task_id: str,
    task_temp: Path,
    now: Callable[[], datetime],
    heartbeat: Callable[[str, int | None], None],
    canceled: Callable[[str], bool] = lambda _task_id: False,
) -> None:
    with session_factory() as database:
        task = database.get(Task, task_id)
        if task is None or task.status != "running":
            raise RuntimeError("active evaluation dataset import not found")
        dataset = database.get(
            EvaluationDataset, str(json.loads(task.payload).get("dataset_id") or "")
        )
        if dataset is None or dataset.deleted_at is not None or not dataset.storage_path:
            raise RuntimeError("evaluation dataset staging file not found")
        archive = (workspace / dataset.storage_path).resolve(strict=True)
        dataset.status = "validating"
        database.commit()
    extracted = task_temp / "dataset"

    def progress(value):
        if canceled(task_id):
            raise EvaluationDatasetCanceled("evaluation dataset import canceled")
        heartbeat(task_id, value)

    metadata = validate_evaluation_zip(archive, extracted, heartbeat=progress)
    target = (
        workspace / "model-projects" / dataset.model_project_id / "evaluation-datasets" / dataset.id
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        shutil.rmtree(target)
    os.replace(extracted, target)
    archive.unlink(missing_ok=True)
    finished = now()
    with session_factory() as database:
        dataset = database.get(EvaluationDataset, dataset.id)
        task = database.get(Task, task_id)
        if dataset is None or task is None:
            raise RuntimeError("evaluation dataset resources disappeared")
        duplicate = database.scalar(
            select(EvaluationDataset).where(
                EvaluationDataset.model_project_id == dataset.model_project_id,
                EvaluationDataset.content_sha256 == metadata["sha256"],
                EvaluationDataset.status == "ready",
                EvaluationDataset.deleted_at.is_(None),
                EvaluationDataset.id != dataset.id,
            )
        )
        if duplicate:
            shutil.rmtree(target, ignore_errors=True)
            raise RuntimeError(f"相同内容的测试集已存在：{duplicate.name}")
        dataset.content_sha256 = metadata["sha256"]
        dataset.storage_path = target.relative_to(workspace).as_posix()
        dataset.classes = json.dumps(metadata["classes"], ensure_ascii=False)
        dataset.image_count = metadata["image_count"]
        dataset.label_count = metadata["label_count"]
        dataset.negative_count = metadata["negative_count"]
        dataset.total_bytes = metadata["total_bytes"]
        dataset.status = "ready"
        dataset.completed_at = finished
        task.status = "succeeded"
        task.progress = 100
        task.result = json.dumps({"dataset_id": dataset.id, "content_sha256": metadata["sha256"]})
        task.finished_at = finished
        task.updated_at = finished
        task.lease_owner = None
        task.lease_expires_at = None
        try:
            database.commit()
        except IntegrityError as exc:
            database.rollback()
            shutil.rmtree(target, ignore_errors=True)
            raise RuntimeError("相同内容的测试集已存在") from exc


def validate_evaluation_zip(archive: Path, target: Path, *, heartbeat=lambda _value: None):
    target.mkdir(parents=True, exist_ok=False)
    digest = hashlib.sha256()
    total_bytes = 0
    seen: set[str] = set()
    entries: list[tuple[zipfile.ZipInfo, str]] = []
    with zipfile.ZipFile(archive) as bundle:
        infos = [item for item in bundle.infolist() if not item.is_dir()]
        if len(infos) > MAX_ENTRIES:
            raise ValueError(f"ZIP 文件条目超过 {MAX_ENTRIES} 个")
        raw_names = []
        for info in infos:
            if info.flag_bits & 0x1:
                raise ValueError("ZIP 不能包含加密文件")
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError("ZIP 不能包含符号链接")
            path = PurePosixPath(unicodedata.normalize("NFC", info.filename.replace("\\", "/")))
            if path.is_absolute() or ".." in path.parts:
                raise ValueError("ZIP 包含不安全路径")
            if any(part in {"__MACOSX", ".DS_Store"} for part in path.parts):
                continue
            raw_names.append(path)
        wrapper = (
            raw_names[0].parts[0]
            if raw_names
            and all(
                len(path.parts) > 1 and path.parts[0] == raw_names[0].parts[0] for path in raw_names
            )
            else None
        )
        for info, path in zip(
            infos,
            [
                PurePosixPath(unicodedata.normalize("NFC", item.filename.replace("\\", "/")))
                for item in infos
            ],
            strict=True,
        ):
            if any(part in {"__MACOSX", ".DS_Store"} for part in path.parts):
                continue
            parts = (
                path.parts[1:]
                if wrapper and path.parts and path.parts[0] == wrapper
                else path.parts
            )
            normalized = PurePosixPath(*parts).as_posix()
            if normalized.casefold() in seen:
                raise ValueError("ZIP 包含大小写或 Unicode 冲突路径")
            seen.add(normalized.casefold())
            if not (
                normalized == "classes.txt"
                or (len(parts) == 2 and parts[0] in {"images", "labels"})
            ):
                raise ValueError("ZIP 仅允许 classes.txt、images/* 和 labels/*")
            limit = MAX_IMAGE_BYTES if parts[0] == "images" else MAX_LABEL_BYTES
            if normalized == "classes.txt":
                limit = MAX_LABEL_BYTES
            if info.file_size > limit:
                raise ValueError(f"文件过大：{normalized}")
            if info.compress_size and info.file_size / info.compress_size > 200:
                raise ValueError(f"压缩比异常：{normalized}")
            total_bytes += info.file_size
            if total_bytes > MAX_EXPANDED_BYTES:
                raise ValueError("ZIP 解压后超过 5 GB")
            entries.append((info, normalized))
        names = {name for _info, name in entries}
        if "classes.txt" not in names:
            raise ValueError("缺少 classes.txt")
        image_names = sorted(name for name in names if name.startswith("images/"))
        if not image_names or len(image_names) > MAX_IMAGES:
            raise ValueError(f"图片数量必须为 1 到 {MAX_IMAGES}")
        label_names = {name for name in names if name.startswith("labels/")}
        by_stem = {PurePosixPath(name).stem.casefold(): name for name in label_names}
        if len(by_stem) != len(label_names):
            raise ValueError("标签文件名存在冲突")
        if {PurePosixPath(name).stem.casefold() for name in image_names} != set(by_stem):
            raise ValueError("每张图片必须有且仅有一个同名 TXT 标签文件")
        for index, (info, normalized) in enumerate(sorted(entries, key=lambda item: item[1])):
            output = target / normalized
            output.parent.mkdir(parents=True, exist_ok=True)
            data = bundle.read(info)
            output.write_bytes(data)
            encoded = normalized.encode("utf-8")
            digest.update(len(encoded).to_bytes(4, "big"))
            digest.update(encoded)
            digest.update(len(data).to_bytes(8, "big"))
            digest.update(data)
            heartbeat(5 + round((index + 1) * 80 / len(entries)))
    classes = [
        unicodedata.normalize("NFC", item.strip())
        for item in (target / "classes.txt").read_text("utf-8-sig").splitlines()
        if item.strip()
    ]
    if not classes or len(set(classes)) != len(classes):
        raise ValueError("classes.txt 类别不能为空或重复")
    for image_name in image_names:
        with Image.open(target / image_name) as image:
            image.verify()
    negative_count = 0
    for label_name in label_names:
        text = (target / label_name).read_text("utf-8-sig").strip()
        if not text:
            negative_count += 1
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            parts = line.split()
            if len(parts) != 5:
                raise ValueError(f"{label_name}:{line_number} 必须为五列 YOLO 标签")
            try:
                class_id = int(parts[0])
                coordinates = [float(value) for value in parts[1:]]
            except ValueError as exc:
                raise ValueError(f"{label_name}:{line_number} 含无效数值") from exc
            if (
                class_id < 0
                or class_id >= len(classes)
                or not all(math.isfinite(value) and 0 <= value <= 1 for value in coordinates)
                or coordinates[2] <= 0
                or coordinates[3] <= 0
            ):
                raise ValueError(f"{label_name}:{line_number} 类别或坐标越界")
    return {
        "sha256": digest.hexdigest(),
        "classes": classes,
        "image_count": len(image_names),
        "label_count": len(label_names),
        "negative_count": negative_count,
        "total_bytes": total_bytes,
    }
