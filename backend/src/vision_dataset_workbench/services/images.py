import math
import os
import shutil
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
import json

from sqlalchemy import Integer, delete, func, select, tuple_
from sqlalchemy.orm import sessionmaker

from ..image_import import fingerprint as import_fingerprint, scan_images, _inside
from ..models import ImageAnnotation, ImageAsset, ImageDirectory, ImageImport, ProjectLabel, Task
from ..storage.paths import HomePathResolver
from .labels import normalize_label_name
from .projects import ProjectForbidden, _record, image_project_write_barrier, touch_project


class ImageNotFound(ValueError):
    pass


class ImageConflict(ValueError):
    pass


def now_utc():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def validate_class_mapping(database, project_id, classes, mappings):
    if len(mappings) != len(classes) or {m["source_id"] for m in mappings} != set(classes):
        raise ValueError("类别映射必须恰好覆盖每个来源编号")
    new_names = set()
    for mapping in mappings:
        label_id, name = mapping.get("project_label_id"), mapping.get("new_label_name")
        if bool(label_id) == bool(name):
            raise ValueError("每个类别必须选择现有标签或新标签名称")
        if label_id:
            label = database.get(ProjectLabel, label_id)
            if label is None or label.project_id != project_id:
                raise ValueError("映射标签不属于当前项目")
        else:
            name = normalize_label_name(name)
            if name in new_names or database.scalar(
                select(ProjectLabel.id).where(
                    ProjectLabel.project_id == project_id, ProjectLabel.name_normalized == name
                )
            ):
                raise ValueError("新标签名称重复，请显式选择现有标签")
            new_names.add(name)
            mapping["new_label_name"] = name


def import_project_state(db, project_id):
    return {
        "images": [
            tuple(row)
            for row in db.execute(
                select(
                    ImageAsset.id,
                    ImageAsset.content_sha256,
                    ImageAsset.directory_id,
                    ImageAsset.source_relative_path,
                )
                .join(ImageDirectory)
                .where(ImageDirectory.project_id == project_id)
                .order_by(ImageAsset.id)
            )
        ],
        "directories": [
            tuple(row)
            for row in db.execute(
                select(
                    ImageDirectory.id,
                    ImageDirectory.name,
                    ImageDirectory.source_relative_path,
                    ImageImport.source_path,
                    ImageImport.status,
                )
                .join(ImageImport)
                .where(ImageDirectory.project_id == project_id)
                .order_by(ImageDirectory.sort_order, ImageDirectory.id)
            )
        ],
    }


class ImageService:
    def __init__(self, engine, settings, workspace, projects):
        self._session_factory = sessionmaker(engine, expire_on_commit=False)
        self.settings, self.workspace, self.projects = settings, workspace.resolve(), projects
        self.paths = HomePathResolver(settings.home)

    def access(self, actor, project_id, *, write=False, execute=False):
        view = self.projects.get_project(actor, project_id)
        if view.project.project_type != "image":
            raise ValueError("图片功能仅适用于图像数据集项目")
        if write and not view.access.allows("project.update"):
            raise ProjectForbidden("project edit permission required")
        if execute and not view.access.allows("task.execute"):
            raise ProjectForbidden("task execute permission required")
        return view

    def _scan(self, project_id, root_path, format=None, ignore_annotations=False):
        _inside(self.paths.home, self.paths.home / root_path)
        with self._session_factory() as db:
            state = import_project_state(db, project_id)
        return scan_images(
            self.paths.resolve_existing(root_path),
            format,
            ignore_annotations=ignore_annotations,
            used_names={row[1] for row in state["directories"]},
            workspace=self.workspace,
        ).plan_import(self.paths.home, state)

    def preview(self, actor, project_id, root_path, format=None, ignore_annotations=False):
        self.access(actor, project_id)
        return self._scan(project_id, root_path, format, ignore_annotations).preview()

    def create_import(
        self,
        actor,
        project_id,
        root_path,
        format,
        fingerprint,
        mappings,
        confirm_warnings,
        ignore_annotations=False,
    ):
        self.access(actor, project_id, write=True, execute=True)
        scan = self._scan(project_id, root_path, format, ignore_annotations)
        if scan.errors:
            raise ValueError("来源存在错误，请修复后重新预检")
        if scan.fingerprint != fingerprint:
            raise ImageConflict("来源或目录名称已变化，请重新预检")
        if not scan.images:
            raise ValueError("没有可新增的图片，所有图片内容均已存在或在本批次内重复")
        if scan.warnings and not confirm_warnings:
            raise ValueError("请确认预检警告")
        at = now_utc()
        with self._session_factory() as db:
            image_project_write_barrier(db, project_id)
            if scan.project_state_fingerprint != import_fingerprint(
                import_project_state(db, project_id)
            ):
                raise ImageConflict("项目图片或目录已变化，请重新预检")
            validate_class_mapping(db, project_id, scan.classes, mappings)
            import_id, task_id = str(uuid4()), str(uuid4())
            task = Task(
                id=task_id,
                project_id=project_id,
                submitted_by_id=actor.id,
                type="import_images",
                status="queued",
                progress=0,
                payload=json.dumps(
                    {
                        "import_id": import_id,
                        "import_state_fingerprint": scan.project_state_fingerprint,
                    }
                ),
                created_at=at,
                updated_at=at,
            )
            db.add(task)
            db.flush()
            batch = ImageImport(
                id=import_id,
                project_id=project_id,
                task_id=task_id,
                created_by_id=actor.id,
                format=scan.format,
                root_name=scan.root.name,
                source_path=scan.root.relative_to(self.paths.home).as_posix(),
                fingerprint=fingerprint,
                class_mapping=json.dumps(mappings),
                status="queued",
                created_at=at,
                updated_at=at,
            )
            db.add(batch)
            touch_project(db, project_id, at=at)
            db.commit()
            return batch, task

    @staticmethod
    def query(
        project_id,
        *,
        directory_id=None,
        search=None,
        annotation_status=None,
        enabled=None,
        label_id=None,
    ):
        query = (
            select(ImageAsset)
            .join(ImageDirectory)
            .join(ImageImport)
            .where(ImageDirectory.project_id == project_id, ImageImport.status == "ready")
        )
        if directory_id:
            values = [directory_id] if isinstance(directory_id, str) else directory_id
            query = query.where(ImageAsset.directory_id.in_(values))
        if search:
            query = query.where(ImageAsset.file_name.contains(search, autoescape=True))
        if annotation_status:
            query = query.where(ImageAsset.annotation_status == annotation_status)
        if enabled is not None:
            query = query.where(ImageAsset.enabled == enabled)
        if label_id:
            query = query.where(
                select(ImageAnnotation.id)
                .where(
                    ImageAnnotation.image_id == ImageAsset.id, ImageAnnotation.label_id == label_id
                )
                .exists()
            )
        return query

    @staticmethod
    def context(db, project_id, image_id):
        image = db.scalar(ImageService.query(project_id).where(ImageAsset.id == image_id))
        if image is None:
            raise ImageNotFound("image not found")
        return image

    @staticmethod
    def annotations(db, ids):
        return (
            list(
                db.scalars(
                    select(ImageAnnotation)
                    .where(ImageAnnotation.image_id.in_(ids))
                    .order_by(ImageAnnotation.sort_order, ImageAnnotation.id)
                )
            )
            if ids
            else []
        )

    def list_images(self, actor, project_id, *, page=1, page_size=50, **filters):
        self.access(actor, project_id)
        with self._session_factory() as db:
            query = self.query(project_id, **filters)
            filtered = query.subquery()
            total, enabled_count, labeled_count = db.execute(
                select(
                    func.count(),
                    func.sum(filtered.c.enabled.cast(Integer)),
                    func.sum((filtered.c.annotation_status == "labeled").cast(Integer)),
                )
            ).one()
            items = list(
                db.scalars(
                    query.order_by(
                        ImageDirectory.sort_order,
                        ImageDirectory.id,
                        ImageAsset.source_relative_path,
                        ImageAsset.id,
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                )
            )
            annotations = self.annotations(db, [i.id for i in items])
            return (
                items,
                annotations,
                total,
                {
                    "enabled_images": enabled_count or 0,
                    "labeled_images": labeled_count or 0,
                },
            )

    def get(self, actor, project_id, image_id):
        self.access(actor, project_id)
        with self._session_factory() as db:
            return self.context(db, project_id, image_id), self.annotations(db, [image_id])

    def directories(self, actor, project_id):
        self.access(actor, project_id)
        with self._session_factory() as db:
            rows = db.execute(
                select(
                    ImageDirectory,
                    func.count(ImageAsset.id),
                    func.sum(ImageAsset.enabled.cast(Integer)),
                    func.sum((ImageAsset.annotation_status == "labeled").cast(Integer)),
                    func.min(ImageAsset.width),
                    func.max(ImageAsset.width),
                    func.min(ImageAsset.height),
                    func.max(ImageAsset.height),
                )
                .select_from(ImageDirectory)
                .join(ImageImport, ImageImport.id == ImageDirectory.import_id)
                .outerjoin(ImageAsset, ImageAsset.directory_id == ImageDirectory.id)
                .where(ImageDirectory.project_id == project_id, ImageImport.status == "ready")
                .group_by(ImageDirectory.id)
                .order_by(ImageDirectory.sort_order, ImageDirectory.id)
            ).all()
            return [
                {
                    "id": d.id,
                    "name": d.name,
                    "source_relative_path": d.source_relative_path,
                    "import_id": d.import_id,
                    "total_images": n,
                    "enabled_images": enabled or 0,
                    "labeled_images": labeled or 0,
                    "min_width": min_w,
                    "max_width": max_w,
                    "min_height": min_h,
                    "max_height": max_h,
                }
                for d, n, enabled, labeled, min_w, max_w, min_h, max_h in rows
            ]

    def file(self, actor, project_id, image_id, *, thumbnail=False):
        image, _ = self.get(actor, project_id, image_id)
        return self.managed_file(project_id, image, thumbnail=thumbnail)

    def managed_file(self, project_id, image, *, thumbnail=False):
        relative = image.thumbnail_path if thumbnail else image.file_path
        root = self.workspace / "projects" / project_id / "images"
        path = self.workspace / relative
        if (
            not root.resolve().is_relative_to(self.workspace.resolve())
            or path.is_symlink()
            or not path.resolve().is_relative_to(root.resolve())
            or not path.is_file()
        ):
            raise ImageNotFound("managed image file not found")
        return path

    def neighbors(self, actor, project_id, image_id, **filters):
        self.access(actor, project_id)
        with self._session_factory() as db:
            current = self.context(db, project_id, image_id)
            directory = db.get(ImageDirectory, current.directory_id)
            columns = (
                ImageDirectory.sort_order,
                ImageDirectory.id,
                ImageAsset.source_relative_path,
                ImageAsset.id,
            )
            anchor = (directory.sort_order, directory.id, current.source_relative_path, current.id)
            query = self.query(project_id, **filters)
            return {
                "previous_id": db.scalar(
                    query.with_only_columns(ImageAsset.id)
                    .where(tuple_(*columns) < anchor)
                    .order_by(*(c.desc() for c in columns))
                    .limit(1)
                ),
                "next_id": db.scalar(
                    query.with_only_columns(ImageAsset.id)
                    .where(tuple_(*columns) > anchor)
                    .order_by(*columns)
                    .limit(1)
                ),
            }

    def replace(self, actor, project_id, image_id, revision, items):
        self.access(actor, project_id, write=True)
        with self._session_factory() as db:
            image_project_write_barrier(db, project_id)
            image = self.context(db, project_id, image_id)
            if image.annotation_revision != revision:
                raise ImageConflict("annotation revision conflict")
            self.validate_annotations(db, project_id, image, items)
            old = {a.id: a for a in self.annotations(db, [image_id])}
            for item in items:
                prior = old.get(item["id"])
                unchanged = prior and all(
                    getattr(prior, key) == item[key]
                    for key in ("label_id", "x_min", "y_min", "x_max", "y_max")
                )
                if unchanged:
                    item["source"], item["confidence"] = prior.source, prior.confidence
                elif prior or item["source"] != "model":
                    item["source"], item["confidence"] = "manual", None
            self.store_annotations(db, image, items, status="labeled")
            touch_project(db, project_id)
            db.commit()
        return self.get(actor, project_id, image_id)

    @staticmethod
    def validate_annotations(db, project_id, image, items):
        ids = [i["id"] for i in items]
        if len(set(ids)) != len(ids):
            raise ValueError("annotation ids must be unique")
        labels = {i["label_id"] for i in items}
        if labels != set(
            db.scalars(
                select(ProjectLabel.id).where(
                    ProjectLabel.project_id == project_id, ProjectLabel.id.in_(labels)
                )
            )
        ):
            raise ValueError("annotation label does not belong to project")
        other = db.scalar(
            select(ImageAnnotation.id).where(
                ImageAnnotation.id.in_(ids), ImageAnnotation.image_id != image.id
            )
        )
        if other:
            raise ValueError("annotation id belongs to another image")
        for item in items:
            values = [item[k] for k in ("x_min", "y_min", "x_max", "y_max")]
            if not all(math.isfinite(v) for v in values) or not (
                0 <= values[0] < values[2] <= image.width
                and 0 <= values[1] < values[3] <= image.height
            ):
                raise ValueError("annotation bounds exceed image dimensions")
            if item["source"] not in {"import", "manual", "model"}:
                raise ValueError("annotation source is invalid")
            confidence = item.get("confidence")
            if confidence is not None and (
                not math.isfinite(confidence) or not 0 <= confidence <= 1
            ):
                raise ValueError("annotation confidence is invalid")

    @staticmethod
    def store_annotations(db, image, items, *, status, operation_id=None):
        db.execute(delete(ImageAnnotation).where(ImageAnnotation.image_id == image.id))
        at = now_utc()
        db.add_all(
            [
                ImageAnnotation(**item, image_id=image.id, sort_order=n, created_at=at)
                for n, item in enumerate(items)
            ]
        )
        image.annotation_status = status
        image.annotation_revision += 1
        image.version += 1
        image.last_auto_operation_id = operation_id
        image.updated_at = at

    def change_enabled(self, actor, project_id, changes, *, by_annotations=False):
        self.access(actor, project_id, write=True)
        with self._session_factory() as db:
            image_project_write_barrier(db, project_id)
            if len({c["image_id"] for c in changes}) != len(changes):
                raise ValueError("duplicate image ids")
            images = []
            for change in changes:
                image = self.context(db, project_id, change["image_id"])
                if image.version != change["version"]:
                    raise ImageConflict("image version conflict")
                image.enabled, image.version, image.updated_at = (
                    bool(self.annotations(db, [image.id])) if by_annotations else change["enabled"],
                    image.version + 1,
                    now_utc(),
                )
                images.append(image)
            touch_project(db, project_id)
            db.commit()
            return images

    @staticmethod
    def _duplicates(db, project_id):
        images = list(
            db.scalars(
                ImageService.query(project_id, enabled=True).order_by(
                    ImageDirectory.sort_order,
                    ImageDirectory.id,
                    ImageAsset.source_relative_path,
                    ImageAsset.id,
                )
            )
        )
        directories = {
            d.id: d
            for d in db.scalars(
                select(ImageDirectory).where(ImageDirectory.project_id == project_id)
            )
        }
        hashes = defaultdict(list)
        for image in images:
            hashes[image.content_sha256].append(image)
        groups = [members for members in hashes.values() if len(members) > 1]

        def item(image):
            return {
                "id": image.id,
                "file_name": image.file_name,
                "directory_name": directories[image.directory_id].name,
            }

        return {
            "fingerprint": import_fingerprint(
                [
                    [
                        i.id,
                        i.content_sha256,
                        i.version,
                        i.annotation_revision,
                        i.source_relative_path,
                        i.file_name,
                        i.directory_id,
                        directories[i.directory_id].sort_order,
                        directories[i.directory_id].name,
                    ]
                    for i in images
                ]
            ),
            "group_count": len(groups),
            "duplicate_count": sum(len(g) - 1 for g in groups),
            "groups": [
                {"keeper": item(g[0]), "duplicates": [item(i) for i in g[1:]]} for g in groups
            ],
        }

    def duplicates(self, actor, project_id):
        self.access(actor, project_id)
        with self._session_factory() as db:
            return self._duplicates(db, project_id)

    def disable_duplicates(self, actor, project_id, expected_fingerprint):
        self.access(actor, project_id, write=True)
        with self._session_factory() as db:
            image_project_write_barrier(db, project_id)
            preview = self._duplicates(db, project_id)
            if preview["fingerprint"] != expected_fingerprint:
                raise ImageConflict("重复图片已变化，请重新预览")
            for group in preview["groups"]:
                for item in group["duplicates"]:
                    image = db.get(ImageAsset, item["id"])
                    image.enabled = False
                    image.version += 1
                    image.updated_at = now_utc()
            touch_project(db, project_id)
            db.commit()
            return {
                "disabled_count": preview["duplicate_count"],
                "group_count": preview["group_count"],
            }

    def delete(self, actor, project_id, items):
        self.access(actor, project_id, write=True)
        moved, archives = [], []
        with self._session_factory() as db:
            image_project_write_barrier(db, project_id)
            if len({i["image_id"] for i in items}) != len(items):
                raise ValueError("duplicate image ids")
            images = [self.context(db, project_id, item["image_id"]) for item in items]
            for image, item in zip(images, items):
                if image.version != item["version"]:
                    raise ImageConflict("image version conflict")
                if image.enabled:
                    raise ImageConflict("仅停用图片允许删除")
            try:
                root = self.workspace / "projects" / project_id / "images"
                for image in images:
                    archive = (
                        self.workspace / ".deleted" / "projects" / project_id / "images" / image.id
                    )
                    _inside(self.workspace, archive)
                    if archive.exists():
                        raise ImageConflict("图片归档已存在")
                    sources = []
                    for relative in (image.file_path, image.thumbnail_path):
                        if Path(relative).is_absolute() or ".." in Path(relative).parts:
                            raise ValueError("受管图片路径必须是安全的相对路径")
                        path = self.workspace / relative
                        _inside(self.workspace, path)
                        if not path.is_relative_to(root) or not path.resolve().is_relative_to(
                            root.resolve()
                        ):
                            raise ValueError("受管图片路径越出项目")
                        if path.exists() and not path.is_file():
                            raise ValueError("受管图片路径不是文件")
                        sources.append(path)
                    archive.mkdir(parents=True)
                    archives.append(archive)
                    metadata = {
                        "deleted_at": now_utc().isoformat() + "Z",
                        "image": _record(image),
                        "annotations": [_record(a) for a in self.annotations(db, [image.id])],
                        "directory": _record(db.get(ImageDirectory, image.directory_id)),
                        "missing": [
                            p.relative_to(self.workspace).as_posix()
                            for p in sources
                            if not p.exists()
                        ],
                    }
                    for source in sources:
                        if not source.exists():
                            continue
                        target = archive / source.relative_to(root)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(source, target)
                        moved.append((source, target))
                    (archive / "metadata.json").write_text(
                        json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
                    )
                    db.delete(image)
                touch_project(db, project_id)
                db.commit()
            except Exception:
                db.rollback()
                # Preserve archives if restoring any file fails, so no remaining data is removed.
                for source, target in reversed(moved):
                    os.replace(target, source)
                for archive in archives:
                    shutil.rmtree(archive)
                raise
        return {"deleted": [i.id for i in images]}
