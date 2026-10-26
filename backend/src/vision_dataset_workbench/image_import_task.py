import json
import os
import shutil
from uuid import uuid4
from collections import Counter

from PIL import Image
from sqlalchemy import select, func

from .image_import import scan_images, file_digest, fingerprint, _inside
from .models import ImageAsset, ImageAnnotation, ImageDirectory, ImageImport, ProjectLabel, Task
from .services.images import import_project_state, validate_class_mapping
from .services.labels import automatic_label_color
from .services.projects import image_project_write_barrier, touch_project
from .storage.materialize import materialize_immutable_file
from .storage.paths import HomePathResolver


class ImageImportCanceled(RuntimeError):
    pass


def execute_image_import(
    session_factory, settings, workspace, task_id, task_temp, now, heartbeat, cancel
):
    with session_factory() as db:
        task = db.get(Task, task_id)
        payload = json.loads(task.payload)
        batch = db.get(ImageImport, payload["import_id"])
        if batch is None:
            raise ValueError("图片导入批次不存在")
        owner = task.lease_owner
        if batch.status == "ready":
            result = json.loads(task.result) if task.result else {}
            ids = result.get("image_ids")
            # Old batches did not record IDs; published files still identify their exact batch.
            prefix = (workspace / "projects" / batch.project_id / "images" / batch.id).relative_to(
                workspace
            ).as_posix() + "/"
            assets = list(
                db.scalars(
                    select(ImageAsset)
                    .join(ImageDirectory)
                    .where(
                        ImageDirectory.project_id == batch.project_id,
                        ImageAsset.id.in_(ids)
                        if ids is not None
                        else ImageAsset.file_path.startswith(prefix, autoescape=True),
                    )
                )
            )
            if (
                not assets
                or (ids is not None and len(assets) != len(ids))
                or (result.get("images") is not None and len(assets) != result["images"])
            ):
                raise ValueError("已发布导入批次没有图片")
            for asset in assets:
                if not asset.file_path.startswith(prefix):
                    raise ValueError("已发布导入批次图片不匹配")
                original, thumbnail = workspace / asset.file_path, workspace / asset.thumbnail_path
                if (
                    not original.is_file()
                    or not thumbnail.is_file()
                    or file_digest(original) != asset.content_sha256
                ):
                    raise ValueError("已发布图片文件缺失或内容变化")
                with Image.open(original) as image:
                    if image.size != (asset.width, asset.height):
                        raise ValueError("已发布图片尺寸变化")
                with Image.open(thumbnail) as image:
                    image.verify()
            image_project_write_barrier(db, batch.project_id, task_id)
            db.refresh(task)
            if task.status != "running" or task.cancel_requested or task.lease_owner != owner:
                raise ImageImportCanceled("图片导入租约或状态已变化")
            task.status, task.progress, task.error, task.finished_at = "succeeded", 100, None, now()
            task.lease_owner, task.lease_expires_at = None, None
            db.commit()
            return
        batch.status, batch.updated_at = "running", now()
        state = import_project_state(db, batch.project_id)
        db.commit()

    def pulse(index, total):
        if cancel(task_id):
            raise ImageImportCanceled("图片导入已取消")
        heartbeat(task_id, int(index / max(1, total) * 40))

    paths = HomePathResolver(settings.home)
    _inside(paths.home, paths.home / batch.source_path)
    scan = scan_images(
        paths.resolve_existing(batch.source_path),
        batch.format,
        used_names={row[1] for row in state["directories"]},
        workspace=workspace,
        heartbeat=pulse,
    )
    source_fingerprint = scan.fingerprint
    scan.plan_import(paths.home, state)
    expected = scan.fingerprint if "import_state_fingerprint" in payload else source_fingerprint
    if scan.errors or expected != batch.fingerprint:
        raise ValueError("来源已变化或含错误，请重新预检并导入")
    if not scan.images:
        raise ValueError("没有可新增的图片，请重新预检")
    staging = task_temp / "images"
    staging.mkdir()
    thumbnails = staging / "thumbnails"
    thumbnails.mkdir()
    destination = workspace / "projects" / batch.project_id / "images" / batch.id
    assets = []
    for index, record in enumerate(scan.images):
        if cancel(task_id):
            raise ImageImportCanceled("图片导入已取消")
        image_id = str(uuid4())
        source = scan.root / record["path"]
        name = image_id + source.suffix.lower()
        method = materialize_immutable_file(source, staging / name)
        if file_digest(staging / name) != record["sha256"]:
            raise ValueError(f"图片内容已变化：{record['path']}")
        with Image.open(staging / name) as image:
            if image.size != (record["width"], record["height"]):
                raise ValueError("图片尺寸已变化")
            image.thumbnail((320, 240))
            image.convert("RGB").save(thumbnails / f"{image_id}.jpg", quality=85)
        assets.append((image_id, name, method, record))
        heartbeat(task_id, 40 + int((index + 1) / len(scan.images) * 55))
    if cancel(task_id):
        raise ImageImportCanceled("图片导入已取消")
    published = False
    try:
        with session_factory() as db:
            image_project_write_barrier(db, batch.project_id, task_id)
            task = db.get(Task, task_id)
            stored = db.get(ImageImport, batch.id)
            if task.status != "running" or task.cancel_requested or task.lease_owner != owner:
                raise ImageImportCanceled("图片导入租约或状态已变化")
            if (
                fingerprint(import_project_state(db, batch.project_id))
                != scan.project_state_fingerprint
            ):
                raise ValueError("项目图片或目录已变化，请重新预检并导入")
            mappings = json.loads(batch.class_mapping)
            if "import_state_fingerprint" not in payload:
                mappings = [m for m in mappings if m["source_id"] in scan.classes]
            validate_class_mapping(db, batch.project_id, scan.classes, mappings)
            labels = {}
            last_order = db.scalar(
                select(func.max(ProjectLabel.sort_order)).where(
                    ProjectLabel.project_id == batch.project_id
                )
            )
            at = now()
            for mapping in mappings:
                label_id = mapping.get("project_label_id")
                if not label_id:
                    label_id = str(uuid4())
                    name = mapping["new_label_name"]
                    last_order = (last_order if last_order is not None else -1) + 1
                    db.add(
                        ProjectLabel(
                            id=label_id,
                            project_id=batch.project_id,
                            name=name,
                            name_normalized=name,
                            description_zh="",
                            color=automatic_label_color(name),
                            enabled=True,
                            version=1,
                            sort_order=last_order,
                            created_at=at,
                            updated_at=at,
                        )
                    )
                labels[mapping["source_id"]] = label_id
            db.flush()
            directories = {}
            base_order = db.scalar(
                select(func.max(ImageDirectory.sort_order)).where(
                    ImageDirectory.project_id == batch.project_id
                )
            )
            for index, group in enumerate(scan.directories):
                if not group["new_images"]:
                    continue
                if "id" in group:
                    directories[group["source_relative_path"]] = group["id"]
                    continue
                directory = ImageDirectory(
                    id=str(uuid4()),
                    project_id=batch.project_id,
                    import_id=batch.id,
                    name=group["name"],
                    source_relative_path=group["source_relative_path"],
                    sort_order=(base_order if base_order is not None else -1) + index + 1,
                    created_at=at,
                )
                directories[group["source_relative_path"]] = directory.id
                db.add(directory)
            db.flush()
            for image_id, name, method, record in assets:
                db.add(
                    ImageAsset(
                        id=image_id,
                        directory_id=directories[record["directory"]],
                        source_relative_path=record.get("stored_path", record["path"]),
                        file_name=(scan.root / record["path"]).name,
                        file_path=(destination / name).relative_to(workspace).as_posix(),
                        thumbnail_path=(destination / "thumbnails" / f"{image_id}.jpg")
                        .relative_to(workspace)
                        .as_posix(),
                        content_sha256=record["sha256"],
                        width=record["width"],
                        height=record["height"],
                        file_size=record["size"],
                        materialization=method,
                        annotation_status=record["annotation_status"],
                        enabled=True,
                        annotation_revision=1,
                        version=1,
                        created_at=at,
                        updated_at=at,
                    )
                )
            db.flush()
            for image_id, _, _, record in assets:
                for order, annotation in enumerate(record["annotations"]):
                    bounds = {key: value for key, value in annotation.items() if key != "source_id"}
                    db.add(
                        ImageAnnotation(
                            id=str(uuid4()),
                            image_id=image_id,
                            label_id=labels[annotation["source_id"]],
                            **bounds,
                            source="import",
                            confidence=None,
                            sort_order=order,
                            created_at=at,
                        )
                    )
            # A crash before DB commit can leave this batch's directory; no ready rows use it.
            if destination.exists():
                shutil.rmtree(destination)
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging, destination)
            published = True
            stored.status, stored.error, stored.updated_at, stored.completed_at = (
                "ready",
                None,
                at,
                at,
            )
            task.status, task.progress, task.error = "succeeded", 100, None
            task.result = json.dumps(
                {
                    "import_id": batch.id,
                    "images": len(assets),
                    "image_ids": [a[0] for a in assets],
                    **{
                        key: value
                        for key, value in scan.import_counts.items()
                        if key != "total_images"
                    },
                    "materializations": dict(Counter(a[2] for a in assets)),
                }
            )
            task.finished_at, task.updated_at = at, at
            task.lease_owner, task.lease_expires_at = None, None
            touch_project(db, batch.project_id, at=at)
            db.commit()
    except Exception:
        if published:
            shutil.rmtree(destination, ignore_errors=True)
        raise
