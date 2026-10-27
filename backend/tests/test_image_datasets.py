"""Image datasets use generated fixtures and an isolated, migrated workspace only."""

import json
import shutil
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, database_url, make_engine
from vision_dataset_workbench.image_dataset_export import export_names, target_train_count
from vision_dataset_workbench.image_import import (
    file_digest,
    parse_detect_line,
    readable_names,
    scan_images,
)
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import (
    DatasetExport,
    ImageAnnotation,
    ImageAsset,
    ImageDirectory,
    ImageImport,
    Project,
    ProjectLabel,
    ProjectMembership,
    Task,
    TrainingModel,
    TrainingTask,
    User,
)
from vision_dataset_workbench.security.passwords import hash_password
from vision_dataset_workbench.services.dataset_exports import (
    DatasetExportConflict,
    DatasetExportService,
    ExportLabelInput,
)
from vision_dataset_workbench.services.images import ImageConflict, ImageNotFound, ImageService
from vision_dataset_workbench.services.projects import ProjectConflict, ProjectService
from vision_dataset_workbench.training.dataset_preparation import (
    dataset_stats,
    materialize_snapshot,
    require_training_samples,
)
from vision_dataset_workbench.worker import TaskWorker

PASSWORD = "correct horse battery staple"
ORIGIN = {"Origin": "http://testserver"}
PROJECT = "image-project"
LABEL = "object-label"


def picture(path, index=0, size=(640, 480), **kwargs):
    path.parent.mkdir(parents=True, exist_ok=True)
    # The pixel color gives each fixture a different content hash, even in large groups.
    Image.new("RGB", size, (index % 256, index // 256 % 256, 71)).save(path, **kwargs)
    return path


def yolo_fixture(root, layout="roboflow", *, missing=True):
    declarations = {}
    for index, split in enumerate(("train", "val", "test")):
        image_dir = f"{split}/images" if layout == "roboflow" else f"images/{split}"
        label_dir = f"{split}/labels" if layout == "roboflow" else f"labels/{split}"
        picture(root / image_dir / f"{split}.png", index)
        labels = root / label_dir
        labels.mkdir(parents=True)
        if split == "train":
            # 0.3 pixels wide in a 640 pixel image; preserve continuous coordinates.
            (labels / f"{split}.txt").write_text("\ufeff0 0.5 0.5 0.00046875 0.2\n", "utf-8")
        elif split == "val" or not missing:
            (labels / f"{split}.txt").write_text("", "utf-8")
        declarations[split] = f"../{image_dir}" if layout == "roboflow" else image_dir
    (root / "data.yaml").write_text(
        yaml.safe_dump({**declarations, "nc": 1, "names": {0: "object"}})
    )
    return root


@pytest.fixture(scope="session")
def password_hash():
    return hash_password(PASSWORD)


@pytest.fixture
def env(tmp_path, password_hash):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    workspace.mkdir(parents=True)
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    with Session(engine, expire_on_commit=False) as db:
        users = {}
        for name in ("owner", "editor", "viewer", "outsider"):
            user = User(
                id=name, username=name, username_normalized=name, password_hash=password_hash
            )
            db.add(user)
            users[name] = user
        db.flush()
        db.add_all(
            [
                Project(id=PROJECT, name="images", project_type="image", creator_id="owner"),
                Project(id="other-project", name="other", project_type="image", creator_id="owner"),
                Project(id="video-project", name="video", creator_id="owner"),
            ]
        )
        db.flush()
        db.add_all(
            [
                ProjectMembership(project_id=PROJECT, user_id="editor", role="editor"),
                ProjectMembership(project_id=PROJECT, user_id="viewer", role="viewer"),
                ProjectLabel(
                    id=LABEL,
                    project_id=PROJECT,
                    name="object",
                    name_normalized="object",
                    color="#16866f",
                    sort_order=0,
                    enabled=True,
                ),
                ProjectLabel(
                    id="other-label",
                    project_id="other-project",
                    name="other",
                    name_normalized="other",
                    color="#16866f",
                    sort_order=0,
                    enabled=True,
                ),
            ]
        )
        db.commit()
    settings = RuntimeSettings(home=home, workspace=workspace)
    projects = ProjectService(engine, settings, workspace)
    worker = TaskWorker(engine, settings, workspace)
    context = SimpleNamespace(
        home=home,
        workspace=workspace,
        engine=engine,
        settings=settings,
        users=users,
        worker=worker,
        projects=projects,
        images=ImageService(engine, settings, workspace, projects),
        exports=DatasetExportService(engine, workspace, projects),
    )
    yield context
    worker._executor.shutdown(wait=True)
    engine.dispose()


def submit_import(env, root, format="yolo_detect", *, mappings=None, confirm=True):
    preview = env.images.preview(
        env.users["owner"], PROJECT, root.relative_to(env.home).as_posix(), format
    )
    assert preview["errors"] == []
    if mappings is None:
        mappings = [
            {"source_id": c["source_id"], "project_label_id": LABEL}
            for c in preview["source_classes"]
        ]
    return env.images.create_import(
        env.users["owner"],
        PROJECT,
        root.relative_to(env.home).as_posix(),
        format,
        preview["fingerprint"],
        mappings,
        confirm,
    )


def run_task(env, task_id, expected="succeeded"):
    claimed = env.worker.claim_available()
    assert task_id in {task.id for task in claimed}
    env.worker.execute_task(task_id)
    with Session(env.engine) as db:
        task = db.get(Task, task_id)
        assert task.status == expected, task.error
        return task.result


def imported(env, root=None, format="yolo_detect"):
    root = root or yolo_fixture(env.home / "source")
    batch, task = submit_import(env, root, format)
    run_task(env, task.id)
    return batch, env.images.list_images(env.users["owner"], PROJECT)[0]


def historical_imported(env, root):
    """Seed legacy duplicates without weakening the current import deduplication contract."""
    originals = {path: path.read_bytes() for path in sorted(root.rglob("*.png"))}
    for index, path in enumerate(originals):
        picture(path, 1000 + index)
    batch, images = imported(env, root, "images")
    with Session(env.engine) as db:
        for path, content in originals.items():
            path.write_bytes(content)
        for image in images:
            content = originals[root / image.source_relative_path]
            target = env.workspace / image.file_path
            target.write_bytes(content)
            stored = db.get(ImageAsset, image.id)
            stored.content_sha256 = file_digest(target)
            stored.file_size = len(content)
        db.commit()
    return batch, env.images.list_images(env.users["owner"], PROJECT)[0]


def rules_for(env, modes=None):
    return [
        {
            "directory_id": d["id"],
            "included": True,
            "mode": (modes or {}).get(d["source_relative_path"], "ratio"),
            "train_ratio": None,
        }
        for d in env.images.directories(env.users["owner"], PROJECT)
    ]


def labels():
    return [ExportLabelInput(LABEL, "object", 0, True)]


def submit_export(env, rules=None, *, ratio=0.8, seed=0):
    rules = rules or rules_for(env)
    preview = env.exports.preview(env.users["owner"], PROJECT, ratio, labels(), rules, seed)
    record = env.exports.create(
        env.users["owner"],
        PROJECT,
        "图片快照",
        ratio,
        labels(),
        directory_rules=rules,
        split_seed=seed,
        preview_fingerprint=preview["fingerprint"],
    )
    return record, preview


def ready_export(env, rules=None, *, ratio=0.8):
    record, preview = submit_export(env, rules, ratio=ratio)
    run_task(env, record.task_id)
    return env.exports.get(env.users["owner"], PROJECT, record.id), preview


def client_for(env, username="owner"):
    from vision_dataset_workbench.capabilities import (
        CapabilityStatus,
        FeatureCapabilities,
        GpuStatus,
        SystemCapabilities,
    )

    unavailable = CapabilityStatus(False, "isolated CPU test")
    capabilities = SystemCapabilities(
        GpuStatus(False, "isolated CPU test", ()),
        unavailable,
        FeatureCapabilities(CapabilityStatus(True), unavailable, unavailable),
    )
    app = create_app(env.settings, capabilities=capabilities)
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/login", headers=ORIGIN, json={"username": username, "password": PASSWORD}
    )
    assert response.status_code == 200, response.text
    return client


def test_pure_images_direct_groups_and_pending(tmp_path):
    root = tmp_path / "pictures"
    for index in range(10):
        picture(root / f"{index}.png", index)
    scan = scan_images(root, "images")
    assert not scan.errors and not scan.warnings
    assert scan.directories == [
        {
            "source_relative_path": ".",
            "name": "pictures",
            "total_images": 10,
            "labeled_images": 0,
            "annotation_count": 0,
        }
    ]
    assert all(i["annotation_status"] == "pending" and not i["annotations"] for i in scan.images)
    picture(root / "nested" / "child.png", 11)
    nested = scan_images(root, "images")
    assert [d["total_images"] for d in nested.directories] == [10, 1]
    assert len(nested.images) == 11


@pytest.mark.parametrize("layout", ["roboflow", "mirror"])
def test_yolo_layout_test_empty_missing_json_and_orphan(tmp_path, layout):
    root = yolo_fixture(tmp_path / "dataset", layout)
    label_dir = "train/labels" if layout == "roboflow" else "labels/train"
    (root / label_dir / "orphan.txt").write_text("0 0.5 0.5 0.2 0.2")
    (root / "annotations.json").write_text('{"shapes": []}')
    scan = scan_images(root, "yolo_detect")
    assert scan.errors == []
    assert len(scan.directories) == 3 and len(scan.images) == 3
    by_file = {Path(i["path"]).name: i for i in scan.images}
    assert by_file["val.png"]["annotation_status"] == "labeled"
    assert by_file["val.png"]["annotations"] == []
    assert by_file["test.png"]["annotation_status"] == "pending"
    assert {w["code"] for w in scan.warnings} == {"missing_label", "orphan_label"}
    assert scan.ignored_files == 1
    box = by_file["train.png"]["annotations"][0]
    assert box["x_max"] - box["x_min"] == pytest.approx(0.3)
    assert "split" not in by_file["test.png"]
    assert "annotations" not in scan.preview()["directories"][0]


@pytest.mark.parametrize("layout", ["roboflow", "mirror"])
def test_classes_txt_or_explicit_mapping_without_yaml(tmp_path, layout):
    root = yolo_fixture(tmp_path / "dataset", layout)
    (root / "data.yaml").unlink()
    scan = scan_images(root, "yolo_detect")
    assert scan.classes == {0: ""}
    assert "missing_classes" in {w["code"] for w in scan.warnings}
    (root / "classes.txt").write_text("\ufeffobject\n", "utf-8")
    scan = scan_images(root, "yolo_detect")
    assert scan.classes == {0: "object"} and not scan.errors


@pytest.mark.parametrize(
    "line",
    [
        "1 0.5 0.5 0.2 0.2",
        "-1 0.5 0.5 0.2 0.2",
        "0.0 0.5 0.5 0.2 0.2",
        "0 0.5 0.5 0.2",
        "0 0.1 0.1 0.9 0.9 0.7 0.7",
        "0 nan 0.5 0.2 0.2",
        "0 0.5 inf 0.2 0.2",
        "0 0.5 0.5 0 0.2",
        "0 0.5 0.5 -0.1 0.2",
        "0 1.1 0.5 0.2 0.2",
        "0 0.5 0.5 1.1 0.2",
        "0 0.01 0.5 0.2 0.2",
    ],
)
def test_invalid_txt_blocks_and_locates_line(tmp_path, line):
    with pytest.raises(ValueError):
        parse_detect_line(line, {0}, 640, 480)
    root = yolo_fixture(tmp_path / "dataset")
    (root / "train/labels/train.txt").write_text("\n" + line)
    scan = scan_images(root, "yolo_detect")
    assert len(scan.errors) == 1
    assert scan.errors[0]["path"] == "train/images/train.png"
    assert "train/labels/train.txt:2:" in scan.errors[0]["message"]
    assert str(root) not in scan.errors[0]["message"]


def test_float_box_tolerance_and_dimensions():
    box = parse_detect_line("0 0.4999999 0.5 1 1", {0}, 640, 480)
    assert box["x_min"] == 0 and box["x_max"] <= 640
    with pytest.raises(ValueError):
        parse_detect_line("0 0.5 0.5 0.2 0.2", {0}, 0, 480)


@pytest.mark.parametrize("kind", ["broken", "exif", "animated"])
def test_invalid_image_encoding_and_orientation(tmp_path, kind):
    root = tmp_path / "images"
    picture(root / "good.png")
    if kind == "broken":
        (root / "bad.png").write_bytes(b"not an image")
    elif kind == "exif":
        exif = Image.Exif()
        exif[274] = 6
        picture(root / "bad.jpg", exif=exif)
    else:
        frames = [Image.new("RGB", (10, 10), color) for color in ("red", "blue")]
        frames[0].save(root / "bad.webp", save_all=True, append_images=frames[1:], duration=100)
    scan = scan_images(root, "images")
    assert len(scan.errors) == 1 and len(scan.images) == 1


@pytest.mark.parametrize("kind", ["outside_file", "outside_dir", "loop", "workspace"])
def test_scan_rejects_symlinks_and_managed_root(tmp_path, kind):
    root = tmp_path / "source"
    picture(root / "good.png")
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = picture(tmp_path / "outside.png")
    if kind == "outside_file":
        (root / "link.png").symlink_to(outside)
    elif kind == "outside_dir":
        (root / "external").symlink_to(tmp_path, target_is_directory=True)
    elif kind == "loop":
        (root / "loop").symlink_to(root, target_is_directory=True)
    else:
        root = workspace
        picture(root / "managed.png")
    with pytest.raises(ValueError):
        scan_images(root, "images", workspace=workspace)


@pytest.mark.parametrize("path", ["../../outside", "train/../../outside", "/unavailable/images"])
def test_yaml_path_escape_is_rejected(tmp_path, path):
    root = yolo_fixture(tmp_path / "dataset")
    config = yaml.safe_load((root / "data.yaml").read_text())
    config["train"] = path
    (root / "data.yaml").write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        scan_images(root, "yolo_detect")


def test_yaml_relocates_legacy_absolute_path_and_rejects_ambiguity(tmp_path):
    root = yolo_fixture(tmp_path / "dataset")
    config = yaml.safe_load((root / "data.yaml").read_text())
    config.update(path="/old/export", train="/old/export/train/images")
    (root / "data.yaml").write_text(yaml.safe_dump(config))
    assert len(scan_images(root, "yolo_detect").images) == 3
    picture(root / "nested/train/images/another.png", 8)
    config.update(path="nested", train="train/images")
    (root / "data.yaml").write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="歧义"):
        scan_images(root, "yolo_detect")


def test_directory_and_export_names_preserve_unique_stems():
    names = readable_names(
        ["a/images", "b/images", "a_images", "UPPER", "upper"], "root", {"a_images"}
    )
    assert len({name.casefold() for name in names.values()}) == 5
    assert names["a/images"] == "a_images_2"
    directories = {"a": {"name": "a/b"}, "b": {"name": "a_b"}, "c": {"name": "很长" * 200}}
    samples = [
        {"image_id": str(index), "directory_id": directory, "source_relative_path": path}
        for index, (directory, path) in enumerate(
            [("a", "same.png"), ("b", "same.jpg"), ("b", "SAME.PNG"), ("c", "verylong.png")]
        )
    ]
    exported = export_names(samples, directories)
    assert len({Path(name).stem.casefold() for name in exported.values()}) == len(samples)
    assert all(len(name.encode("utf-8")) <= 255 and "/" not in name for name in exported.values())


def test_worker_import_edit_export_round_trip_and_source_removal(env):
    root = yolo_fixture(env.home / "source")
    original_txt = (root / "train/labels/train.txt").read_bytes()
    batch, images = imported(env, root)
    assert len(images) == 3
    positive = next(i for i in images if i.file_name == "train.png")
    image, boxes = env.images.get(env.users["owner"], PROJECT, positive.id)
    assert boxes[0].source == "import" and boxes[0].confidence is None
    assert boxes[0].x_max - boxes[0].x_min == pytest.approx(0.3)
    item = {
        k: getattr(boxes[0], k)
        for k in ("id", "label_id", "x_min", "y_min", "x_max", "y_max", "source", "confidence")
    }
    item["y_min"] += 0.1
    updated, boxes = env.images.replace(env.users["owner"], PROJECT, image.id, 1, [item])
    assert updated.annotation_revision == 2 and boxes[0].source == "manual"
    assert (root / "train/labels/train.txt").read_bytes() == original_txt
    target = env.workspace / "projects" / PROJECT / "images" / batch.id
    assert not list(target.rglob("*.txt"))
    for image in images:
        assert env.images.file(env.users["owner"], PROJECT, image.id).is_file()
        with Image.open(
            env.images.file(env.users["owner"], PROJECT, image.id, thumbnail=True)
        ) as thumb:
            assert thumb.size == (320, 240) and thumb.mode == "RGB"
    shutil.rmtree(root)
    rules = rules_for(env, {"train/images": "train", "val/images": "val", "test/images": "train"})
    record, preview = ready_export(env, rules)
    assert preview["total_samples"] == 3 and preview["excluded"] == {}
    manifest = json.loads(record.manifest)
    assert manifest["version"] == 2 and manifest["project_type"] == "image"
    assert manifest["total_samples"] == 3 and manifest["positive_samples"] == {"train": 1, "val": 0}
    _, path = env.exports.download_directory(env.users["owner"], PROJECT, record.id)
    files = list((path / "train/labels").glob("*.txt"))
    box = parse_detect_line(
        next(p for p in files if p.read_text()).read_text().strip(), {0}, 640, 480
    )
    assert box["x_max"] - box["x_min"] == pytest.approx(0.3, abs=0.0001)
    assert next((path / "val/labels").iterdir()).read_text() == ""
    assert dataset_stats(path) == {
        "train_images": 2,
        "val_images": 1,
        "train_annotations": 1,
        "val_annotations": 0,
    }
    require_training_samples(dataset_stats(path))


def test_pure_pending_exports_as_negative_without_confirmation(env):
    root = env.home / "pure"
    picture(root / "one.png")
    imported(env, root, "images")
    record, preview = ready_export(env)
    assert preview["total_samples"] == 1 and preview["excluded"] == {}
    manifest = json.loads(record.manifest)
    assert manifest["total_samples"] == 1 and manifest["negative_samples"]["train"] == 1
    with pytest.raises(ValueError, match="同时包含"):
        require_training_samples(dataset_stats(env.workspace / record.storage_path))


def test_directory_ratios_400_images_and_determinism(env):
    root = env.home / "four"
    for index, group in enumerate(("fixed_train", "fixed_val", "default", "custom")):
        for n in range(100):
            picture(root / group / f"{n:03}.png", index * 100 + n, size=(8, 8))
    _, images = imported(env, root, "images")
    rules = rules_for(env, {"fixed_train": "train", "fixed_val": "val"})
    custom_id = next(
        d["id"]
        for d in env.images.directories(env.users["owner"], PROJECT)
        if d["source_relative_path"] == "custom"
    )
    next(r for r in rules if r["directory_id"] == custom_id)["train_ratio"] = 0.6
    preview = env.exports.preview(env.users["owner"], PROJECT, 0.8, labels(), rules, 42)
    assert (preview["total_samples"], preview["train_samples"], preview["val_samples"]) == (
        400,
        240,
        160,
    )
    assert preview["actual_train_ratio"] == 0.6
    assert preview == env.exports.preview(env.users["owner"], PROJECT, 0.8, labels(), rules, 42)
    assert all(d["deviation"] == 0 for d in preview["directory_stats"])


@pytest.mark.parametrize("count,expected", [(1, 1), (2, 1), (3, 2)])
def test_small_directory_rounding(count, expected):
    assert target_train_count(count, 0.8) == expected


def test_duplicates_stay_together_and_pin_conflicts(env):
    root = env.home / "duplicates"
    first = picture(root / "a/one.png")
    (root / "b").mkdir()
    shutil.copyfile(first, root / "b/two.png")
    shutil.copyfile(first, root / "a/again.png")
    _, images = historical_imported(env, root)
    rules = rules_for(env)
    record, preview = ready_export(env, rules, ratio=0.5)
    manifest = json.loads(record.manifest)
    assert len({s["split"] for s in manifest["samples"]}) == 1
    assert any(d["deviation_reason"] == "exact_content_groups" for d in preview["directory_stats"])
    rules = rules_for(env, {"a": "train", "b": "val"})
    with pytest.raises(ImageConflict, match="同时指定"):
        env.exports.preview(env.users["owner"], PROJECT, 0.8, labels(), rules)
    with pytest.raises(ImageConflict, match="同时指定"):
        env.exports.create(
            env.users["owner"],
            PROJECT,
            "conflict",
            0.8,
            labels(),
            directory_rules=rules,
            preview_fingerprint="0" * 64,
        )
    env.images.replace(
        env.users["owner"],
        PROJECT,
        images[0].id,
        1,
        [
            dict(
                id="manual-box",
                label_id=LABEL,
                x_min=1.0,
                y_min=1.0,
                x_max=2.0,
                y_max=2.0,
                source="manual",
                confidence=None,
            )
        ],
    )
    with pytest.raises(ImageConflict, match="状态或标注不一致"):
        env.exports.preview(env.users["owner"], PROJECT, 0.8, labels(), rules_for(env))


@pytest.mark.parametrize("operation", ["cancel", "source_changed", "publish_failure", "lease_lost"])
def test_import_is_atomic_on_cancel_failure_and_lease_loss(env, monkeypatch, operation):
    root = yolo_fixture(env.home / "source")
    batch, task = submit_import(
        env, root, mappings=[{"source_id": 0, "new_label_name": "new_object"}]
    )
    assert env.images.directories(env.users["owner"], PROJECT) == []
    if operation == "source_changed":
        (root / "train/labels/train.txt").write_text("0 0.5 0.5 0.2 0.2")
    elif operation == "publish_failure":
        import vision_dataset_workbench.image_import_task as implementation

        def fail_publish(*args):
            raise OSError("simulated publication failure")

        monkeypatch.setattr(implementation.os, "replace", fail_publish)
    else:
        original = env.worker._heartbeat

        def interrupted(task_id, progress):
            original(task_id, progress)
            if progress >= 40:
                with Session(env.engine) as db:
                    stored = db.get(Task, task_id)
                    if operation == "cancel":
                        stored.cancel_requested = True
                    else:
                        stored.lease_owner = "replacement-worker"
                    db.commit()

        monkeypatch.setattr(env.worker, "_heartbeat", interrupted)
    expected = {"cancel": "canceled", "lease_lost": "running"}.get(operation, "failed")
    run_task(env, task.id, expected)
    assert env.images.directories(env.users["owner"], PROJECT) == []
    assert env.images.list_images(env.users["owner"], PROJECT)[2] == 0
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageAsset.id))) == 0
        assert db.scalar(select(func.count(ImageAnnotation.id))) == 0
        assert (
            db.scalar(select(func.count(ProjectLabel.id)).where(ProjectLabel.name == "new_object"))
            == 0
        )
        if operation != "lease_lost":
            assert db.get(ImageImport, batch.id).status == expected
        else:
            assert db.get(Task, task.id).lease_owner == "replacement-worker"
    assert not (env.workspace / "projects" / PROJECT / "images" / batch.id).exists()
    assert not list((env.workspace / "tmp").iterdir())


@pytest.mark.parametrize("published", [False, True])
def test_expired_import_lease_recovers_and_ready_replay_is_idempotent(env, published):
    root = yolo_fixture(env.home / "source")
    batch, task = submit_import(env, root)
    if published:
        run_task(env, task.id)
        shutil.rmtree(root)
    else:
        orphan = env.workspace / "projects" / PROJECT / "images" / batch.id
        orphan.mkdir(parents=True)
        (orphan / "uncommitted.txt").write_text("orphaned previous attempt")
    with Session(env.engine) as db:
        old = db.get(Task, task.id)
        old.status = "running"
        old.lease_owner = "dead-worker"
        old.lease_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=5
        )
        db.commit()
    run_task(env, task.id)
    with Session(env.engine) as db:
        assert db.get(ImageImport, batch.id).status == "ready"
        assert db.scalar(select(func.count(ImageAsset.id))) == 3
        assert db.scalar(select(func.count(ImageDirectory.id))) == 3
        assert db.scalar(select(func.count(ImageAnnotation.id))) == 1
        assert db.get(Task, task.id).lease_owner is None
    assert not list((env.workspace / "projects" / PROJECT / "images" / batch.id).rglob("*.txt"))


@pytest.mark.parametrize("operation", ["cancel", "source_changed", "revision_changed"])
def test_export_failure_and_cancel_do_not_publish(env, monkeypatch, operation):
    _, images = imported(env)
    record, _ = submit_export(env)
    if operation == "source_changed":
        image = next(i for i in images if i.file_name == "train.png")
        (env.workspace / image.file_path).write_bytes(b"changed content")
    elif operation == "revision_changed":
        with Session(env.engine) as db:
            # Bypass the public write barrier to simulate a corrupted frozen input.
            db.get(
                ImageAsset, next(i.id for i in images if i.file_name == "train.png")
            ).version += 1
            db.commit()
    else:
        original = env.worker._heartbeat

        def cancel_after_image(task_id, progress):
            original(task_id, progress)
            with Session(env.engine) as db:
                db.get(Task, task_id).cancel_requested = True
                db.commit()

        monkeypatch.setattr(env.worker, "_heartbeat", cancel_after_image)
    run_task(env, record.task_id, "canceled" if operation == "cancel" else "failed")
    stored = env.exports.get(env.users["owner"], PROJECT, record.id)
    assert stored.storage_path is None and stored.manifest is None
    assert not list((env.workspace / "projects" / PROJECT / "exports").glob("*"))
    assert not list((env.workspace / "tmp").iterdir())


def test_import_warnings_mapping_validation_and_fingerprint(env):
    root = yolo_fixture(env.home / "source")
    preview = env.images.preview(env.users["owner"], PROJECT, "source", "yolo_detect")
    with pytest.raises(ValueError, match="警告"):
        submit_import(env, root, confirm=False)
    for mapping in (
        [],
        [{"source_id": 0, "project_label_id": "other-label"}],
        [{"source_id": 0, "project_label_id": LABEL, "new_label_name": "new"}],
        [{"source_id": 0, "new_label_name": "OBJECT"}],
    ):
        with pytest.raises(ValueError):
            submit_import(env, root, mappings=mapping)
    (root / "train/labels/train.txt").write_text("0 0.5 0.5 0.2 0.2")
    with pytest.raises(ImageConflict, match="已变化"):
        env.images.create_import(
            env.users["owner"],
            PROJECT,
            "source",
            "yolo_detect",
            preview["fingerprint"],
            [{"source_id": 0, "project_label_id": LABEL}],
            True,
        )
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageImport.id))) == 0
        assert db.scalar(select(func.count(Task.id))) == 0


@pytest.mark.parametrize("task_type", ["import_images", "auto_annotate", "export_dataset"])
@pytest.mark.parametrize("status", ["queued", "running"])
def test_write_barrier_blocks_mutations_and_labels_without_bumping_project(env, task_type, status):
    _, images = imported(env)
    from vision_dataset_workbench.services.labels import LabelService

    with Session(env.engine) as db:
        before = (db.get(Project, PROJECT).version, db.get(Project, PROJECT).updated_at)
        db.add(
            Task(
                id="busy",
                project_id=PROJECT,
                submitted_by_id="owner",
                type=task_type,
                status=status,
            )
        )
        db.commit()
    for operation in (
        lambda: env.images.change_enabled(
            env.users["owner"],
            PROJECT,
            [{"image_id": images[0].id, "version": 1, "enabled": False}],
        ),
        lambda: env.images.change_enabled(
            env.users["owner"],
            PROJECT,
            [{"image_id": images[0].id, "version": 1}],
            by_annotations=True,
        ),
        lambda: env.images.disable_duplicates(env.users["owner"], PROJECT, "0" * 64),
        lambda: env.images.delete(
            env.users["owner"], PROJECT, [{"image_id": images[0].id, "version": 1}]
        ),
        lambda: env.images.replace(env.users["owner"], PROJECT, images[0].id, 1, []),
        lambda: LabelService(env.engine, env.projects).create_label(
            env.users["owner"], PROJECT, "blocked", "", "#16866f"
        ),
    ):
        with pytest.raises(ProjectConflict):
            operation()
    with Session(env.engine) as db:
        assert (db.get(Project, PROJECT).version, db.get(Project, PROJECT).updated_at) == before
        assert db.get(ImageAsset, images[0].id).version == 1


def test_concurrent_import_submission_allows_only_one_writer(env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    yolo_fixture(env.home / "source")
    preview = env.images.preview(env.users["owner"], PROJECT, "source", "yolo_detect")
    barrier = Barrier(2)

    def submit(_):
        barrier.wait(timeout=5)
        try:
            env.images.create_import(
                env.users["owner"],
                PROJECT,
                "source",
                "yolo_detect",
                preview["fingerprint"],
                [{"source_id": 0, "project_label_id": LABEL}],
                True,
            )
            return "created"
        except ProjectConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(submit, range(2)))
    assert sorted(results) == ["conflict", "created"]
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageImport.id))) == 1
        assert db.scalar(select(func.count(Task.id))) == 1


def test_annotation_revision_empty_save_bounds_and_atomic_bulk(env):
    _, images = imported(env)
    pending = next(i for i in images if i.annotation_status == "pending")
    positive = next(i for i in images if i.file_name == "train.png")
    with pytest.raises(ImageConflict):
        env.images.replace(env.users["owner"], PROJECT, pending.id, 2, [])
    box = dict(
        id="invalid", label_id=LABEL, x_min=1.0, y_min=1.0, x_max=641.0, y_max=20.0, source="manual"
    )
    with pytest.raises(ValueError, match="bounds"):
        env.images.replace(env.users["owner"], PROJECT, pending.id, 1, [box])
    box.update(label_id="other-label", x_max=2.0)
    with pytest.raises(ValueError, match="label"):
        env.images.replace(env.users["owner"], PROJECT, pending.id, 1, [box])
    with pytest.raises(ImageConflict):
        env.images.change_enabled(
            env.users["owner"],
            PROJECT,
            [
                {"image_id": pending.id, "version": 1, "enabled": False},
                {"image_id": positive.id, "version": 100, "enabled": False},
            ],
        )
    current, _ = env.images.get(env.users["owner"], PROJECT, pending.id)
    assert current.enabled and current.version == 1 and current.annotation_status == "pending"
    updated, boxes = env.images.replace(env.users["owner"], PROJECT, pending.id, 1, [])
    assert updated.annotation_status == "labeled" and updated.annotation_revision == 2 and not boxes


@pytest.mark.parametrize(
    "invalid", ["missing", "duplicate", "unknown", "excluded", "pin_ratio", "nan"]
)
def test_directory_rule_validation(env, invalid):
    imported(env)
    rules = rules_for(env)
    if invalid == "missing":
        rules.pop()
    elif invalid == "duplicate":
        rules[0] = rules[1].copy()
    elif invalid == "unknown":
        rules[0]["directory_id"] = "foreign-directory"
    elif invalid == "excluded":
        for rule in rules:
            rule["included"] = False
    elif invalid == "pin_ratio":
        rules[0].update(mode="train", train_ratio=0.8)
    else:
        rules[0]["train_ratio"] = float("nan")
    with pytest.raises(ValueError):
        env.exports.preview(env.users["owner"], PROJECT, 0.8, labels(), rules)


def test_export_fingerprint_tracks_enabled_label_and_rule_changes(env):
    _, images = imported(env)
    rules = rules_for(env)
    preview = env.exports.preview(env.users["owner"], PROJECT, 0.8, labels(), rules)
    env.images.change_enabled(
        env.users["owner"], PROJECT, [{"image_id": images[0].id, "version": 1, "enabled": False}]
    )
    with pytest.raises(DatasetExportConflict, match="重新预览"):
        env.exports.create(
            env.users["owner"],
            PROJECT,
            "stale",
            0.8,
            labels(),
            directory_rules=rules,
            preview_fingerprint=preview["fingerprint"],
        )
    fresh = env.exports.preview(env.users["owner"], PROJECT, 0.8, labels(), rules)
    assert fresh["fingerprint"] != preview["fingerprint"]
    with Session(env.engine) as db:
        db.get(ProjectLabel, LABEL).version += 1
        db.commit()
    after_label = env.exports.preview(env.users["owner"], PROJECT, 0.8, labels(), rules)
    assert after_label["fingerprint"] != fresh["fingerprint"]
    changed_ratio = env.exports.preview(env.users["owner"], PROJECT, 0.7, labels(), rules)
    assert (changed_ratio["train_samples"], changed_ratio["val_samples"]) == (
        after_label["train_samples"],
        after_label["val_samples"],
    )
    assert after_label["fingerprint"] != changed_ratio["fingerprint"]
    with pytest.raises(DatasetExportConflict, match="重新预览"):
        env.exports.create(
            env.users["owner"],
            PROJECT,
            "changed ratio",
            0.7,
            labels(),
            directory_rules=rules,
            preview_fingerprint=after_label["fingerprint"],
        )


@pytest.mark.parametrize(
    "kind",
    [
        "task_single",
        "task_multi",
        "model_single",
        "model_multi",
        "frozen_single",
        "frozen_multi",
        "malformed",
    ],
)
def test_training_references_protect_snapshot_files_and_project(env, kind):
    imported(env)
    record, _ = ready_export(env)
    path = env.workspace / record.storage_path
    with Session(env.engine) as db:
        task = TrainingTask(id="training", code="training", name="training", created_by_id="owner")
        if kind == "task_single":
            task.default_dataset_export_id = record.id
        elif kind == "task_multi":
            task.default_dataset_mode = "multi"
            task.default_multi_dataset_config = json.dumps({"dataset_export_ids": [record.id]})
        db.add(task)
        db.flush()
        model = TrainingModel(id="training-model", training_task_id=task.id, name="model")
        if kind == "model_single":
            model.dataset_export_id = record.id
        elif kind == "model_multi":
            model.dataset_mode = "multi"
            model.multi_dataset_config = json.dumps({"dataset_export_ids": [record.id]})
        elif kind == "frozen_single":
            model.dataset_snapshot = json.dumps({"id": record.id})
        elif kind == "frozen_multi":
            model.dataset_snapshot = json.dumps({"sources": [{"dataset_export_id": record.id}]})
        elif kind == "malformed":
            model.dataset_snapshot = "not-json"
        db.add(model)
        db.commit()
    with pytest.raises((DatasetExportConflict, ProjectConflict)):
        env.exports.delete(env.users["owner"], PROJECT, record.id)
    assert path.is_dir()
    with Session(env.engine) as db:
        assert db.get(DatasetExport, record.id).deleted_at is None
    with pytest.raises(ProjectConflict):
        env.projects.delete_project(env.users["owner"], PROJECT)
    assert path.is_dir()


def test_single_side_exports_can_be_combined_as_training_input(env):
    imported(env)
    directories = ["train/images", "val/images", "test/images"]
    train, _ = ready_export(env, rules_for(env, dict.fromkeys(directories, "train")))
    val, _ = ready_export(env, rules_for(env, dict.fromkeys(directories, "val")))
    for record in (train, val):
        with pytest.raises(ValueError, match="同时包含"):
            require_training_samples(dataset_stats(env.workspace / record.storage_path))
    snapshot = {
        "target_classes": ["object"],
        "sources": [
            {
                "dataset_export_id": record.id,
                "storage_path": record.storage_path,
                "class_map": {"0": 0},
            }
            for record in (train, val)
        ],
    }
    target = env.workspace / "training" / "prepared"
    stats = materialize_snapshot(snapshot, env.workspace, target)
    assert stats["train_images"] == stats["val_images"] == 3
    assert stats["train_annotations"] == stats["val_annotations"] == 1
    assert (target / "READY").is_file()
    assert materialize_snapshot(snapshot, env.workspace, target)["train_images"] == 3


@pytest.mark.parametrize(
    "username,read,write",
    [("owner", 200, 202), ("editor", 200, 202), ("viewer", 200, 403), ("outsider", 404, 404)],
)
def test_api_import_permissions_and_no_absolute_source_paths(env, username, read, write):
    yolo_fixture(env.home / "source")
    client = client_for(env, username)
    base = f"/api/v1/projects/{PROJECT}"
    preview = client.post(
        base + "/image-imports/preview",
        headers=ORIGIN,
        json={"root_path": "source", "format": "yolo_detect"},
    )
    assert preview.status_code == read, preview.text
    assert str(env.home) not in preview.text
    fingerprint = preview.json().get("fingerprint", "0" * 64)
    response = client.post(
        base + "/image-imports",
        headers=ORIGIN,
        json={
            "root_path": "source",
            "format": "yolo_detect",
            "fingerprint": fingerprint,
            "class_mapping": [{"source_id": 0, "project_label_id": LABEL}],
            "confirm_warnings": True,
        },
    )
    assert response.status_code == write, response.text
    if write == 202:
        run_task(env, response.json()["task"]["id"])
        assert client.get(base + "/images").json()["total"] == 3


@pytest.mark.parametrize(
    "username,read,write",
    [("owner", 200, 200), ("editor", 200, 200), ("viewer", 200, 403), ("outsider", 404, 404)],
)
def test_api_image_and_export_read_write_permissions(env, username, read, write):
    _, images = imported(env)
    record, _ = ready_export(env)
    image = images[0]
    client = client_for(env, username)
    base = f"/api/v1/projects/{PROJECT}"
    for suffix in ("", "/file", "/thumbnail", "/annotations", "/neighbors"):
        response = client.get(base + f"/images/{image.id}" + suffix)
        assert response.status_code == read, response.text
    response = client.get(base + f"/dataset-exports/{record.id}/download")
    assert response.status_code == read, response.text
    response = client.post(
        base + "/images/enabled",
        headers=ORIGIN,
        json={"changes": [{"image_id": image.id, "version": 1, "enabled": False}]},
    )
    assert response.status_code == write, response.text
    assert client.get(f"/api/v1/projects/other-project/images/{image.id}/file").status_code == 404


def test_api_same_origin_paths_project_type_and_conflicts(env):
    _, images = imported(env)
    client = client_for(env)
    base = f"/api/v1/projects/{PROJECT}"
    image = images[0]
    payload = {"changes": [{"image_id": image.id, "version": 1, "enabled": False}]}
    assert (
        client.post(
            base + "/images/enabled", headers={"Origin": "http://evil.example"}, json=payload
        ).status_code
        == 403
    )
    assert client.post(base + "/images/enabled", headers=ORIGIN, json=payload).status_code == 200
    assert client.post(base + "/images/enabled", headers=ORIGIN, json=payload).status_code == 409
    assert client.get(base + "/images", params={"page_size": 51}).status_code == 422
    for path in ("../outside", str(env.home / "source"), ".vision-dataset-workbench"):
        assert (
            client.post(
                base + "/image-imports/preview",
                headers=ORIGIN,
                json={"root_path": path, "format": "images"},
            ).status_code
            == 422
        )
    assert client.get("/api/v1/projects/video-project/images").status_code == 422
    assert client.get(f"/api/v1/projects/other-project/images/{image.id}").status_code == 404


def auto_task(env, images):
    task_id = "fake-auto"
    payload = {
        "scope_type": "image",
        "images": [
            {"id": image.id, "revision": image.annotation_revision, "version": image.version}
            for image in images
        ],
        "source": "local",
        "model_id": "unused-fake-model",
        "overwrite": False,
    }
    with Session(env.engine) as db:
        db.add(
            Task(
                id=task_id,
                project_id=PROJECT,
                submitted_by_id="owner",
                type="auto_annotate",
                payload=json.dumps(payload),
            )
        )
        db.commit()
    return task_id


@pytest.mark.parametrize(
    "scenario", ["zero", "positive", "cancel", "expired_lease", "ready_replay", "stale_revision"]
)
def test_real_auto_worker_states_cancellation_revision_and_idempotency(env, monkeypatch, scenario):
    from unittest.mock import Mock

    root = env.home / "pure"
    for index in range(3):
        picture(root / f"{index}.png", index)
    _, images = imported(env, root, "images")
    task_id = auto_task(env, images)
    detections = (
        []
        if scenario == "zero"
        else [
            SimpleNamespace(
                label="object", x_min=10.0, y_min=20.0, x_max=10.3, y_max=40.0, confidence=0.9
            )
        ]
    )
    predictor = Mock(return_value=detections)
    monkeypatch.setattr(env.worker, "_auto_predictor", lambda *args: predictor)
    original_heartbeat = env.worker._heartbeat

    class SimulatedCrash(BaseException):
        pass

    def interrupt_after_commit(task_id, progress):
        original_heartbeat(task_id, progress)
        if scenario == "expired_lease":
            raise SimulatedCrash()
        with Session(env.engine) as db:
            db.get(Task, task_id).cancel_requested = True
            db.commit()

    if scenario in {"cancel", "expired_lease"}:
        monkeypatch.setattr(env.worker, "_heartbeat", interrupt_after_commit)
    if scenario == "stale_revision":
        with Session(env.engine) as db:
            db.get(ImageAsset, images[0].id).annotation_revision += 1
            db.commit()
        run_task(env, task_id, "failed")
        with Session(env.engine) as db:
            assert "已变化" in db.get(Task, task_id).error
            assert db.scalar(select(func.count(ImageAnnotation.id))) == 0
        assert predictor.call_count == 0
        return
    if scenario == "expired_lease":
        with pytest.raises(SimulatedCrash):
            run_task(env, task_id)
        with Session(env.engine) as db:
            assert db.scalar(select(func.count(ImageAnnotation.id))) == 1
    else:
        run_task(env, task_id, "canceled" if scenario == "cancel" else "succeeded")
    if scenario in {"expired_lease", "ready_replay"}:
        with Session(env.engine) as db:
            task = db.get(Task, task_id)
            task.status, task.lease_owner = "running", "dead-worker"
            task.lease_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
                minutes=5
            )
            db.commit()
        monkeypatch.setattr(env.worker, "_heartbeat", original_heartbeat)
        run_task(env, task_id)
    with Session(env.engine) as db:
        stored = [db.get(ImageAsset, image.id) for image in images]
        boxes = list(db.scalars(select(ImageAnnotation)))
        expected_processed = 1 if scenario == "cancel" else 3
        assert predictor.call_count == expected_processed
        assert sum(i.last_auto_operation_id == task_id for i in stored) == expected_processed
        assert len(boxes) == (0 if scenario == "zero" else expected_processed)
        assert all(
            i.version == 2 and i.annotation_revision == 2 for i in stored[:expected_processed]
        )
        if scenario == "zero":
            assert all(i.annotation_status == "pending" for i in stored)
        else:
            assert all(i.annotation_status == "labeled" for i in stored[:expected_processed])
            assert all(
                b.source == "model" and b.x_max - b.x_min == pytest.approx(0.3) for b in boxes
            )
        if scenario == "cancel":
            assert all(i.annotation_status == "pending" and i.version == 1 for i in stored[1:])


def test_0028_upgrade_preserves_video_annotations_active_tasks_exports_and_trigger(
    tmp_path, monkeypatch
):
    from sqlalchemy.exc import IntegrityError
    from vision_dataset_workbench.models import Frame, FrameAnnotation, Video

    path = tmp_path / "historical.sqlite3"
    monkeypatch.setenv("VDW_DATABASE_URL", database_url(path).render_as_string(hide_password=False))
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    command.upgrade(config, "0028_resource_activity_timestamps")
    engine = make_engine(path)
    at = datetime(2026, 1, 1)
    with Session(engine) as db:
        db.add(
            User(
                id="historical-owner",
                username="historical",
                username_normalized="historical",
                password_hash="hash",
            )
        )
        db.flush()
        db.connection().exec_driver_sql(
            "INSERT INTO projects (id,name,description,creator_id,version,created_at,updated_at) VALUES (?,?, '',?,1,?,?)",
            ("historical-project", "history", "historical-owner", at, at),
        )
        db.add(
            ProjectLabel(
                id="historical-label",
                project_id="historical-project",
                name="object",
                name_normalized="object",
                color="#16866f",
                sort_order=0,
            )
        )
        db.add(
            Video(
                id="historical-video",
                project_id="historical-project",
                short_code="ABCDEFGH",
                source_type="local",
                title="video",
                status="ready",
            )
        )
        db.flush()
        db.add(
            Frame(
                id="historical-frame",
                video_id="historical-video",
                generation=1,
                sequence=1,
                source_frame_index=0,
                time_offset=0,
                file_path="frames/historical.jpg",
            )
        )
        db.add_all(
            [
                Task(
                    id="active-task",
                    project_id="historical-project",
                    video_id="historical-video",
                    submitted_by_id="historical-owner",
                    type="extract_frames",
                    status="running",
                    progress=31,
                    lease_owner="existing-worker",
                    lease_expires_at=at + timedelta(days=3650),
                    payload='{"generation": 1}',
                ),
                Task(
                    id="export-task",
                    project_id="historical-project",
                    submitted_by_id="historical-owner",
                    type="export_dataset",
                    status="succeeded",
                    payload='{"export_id": "historical-export"}',
                ),
            ]
        )
        db.flush()
        db.add(
            FrameAnnotation(
                id="historical-box",
                frame_id="historical-frame",
                label_id="historical-label",
                x_min=1,
                y_min=2,
                x_max=3,
                y_max=4,
                source="manual",
            )
        )
        db.add(
            DatasetExport(
                id="historical-export",
                project_id="historical-project",
                task_id="export-task",
                created_by_id="historical-owner",
                name="legacy",
                status="ready",
                train_ratio=0.8,
                label_snapshot="[]",
                source_snapshot='{"videos": [{"video_id": "historical-video"}]}',
                total_frames=1,
                train_frames=1,
                val_frames=0,
            )
        )
        db.commit()
    with sqlite3.connect(path) as db:
        tables = ("videos", "frames", "annotations", "tasks", "dataset_exports")
        before = {
            table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() for table in tables
        }
        trigger = db.execute(
            "SELECT sql FROM sqlite_master WHERE name='trg_videos_project_limit'"
        ).fetchone()[0]
    engine.dispose()
    command.upgrade(config, "0029_image_datasets")
    with sqlite3.connect(path) as db:
        assert before == {
            table: db.execute(f"SELECT * FROM {table} ORDER BY id").fetchall() for table in tables
        }
        assert db.execute(
            "SELECT project_type FROM projects WHERE id='historical-project'"
        ).fetchone() == ("video",)
        assert db.execute("PRAGMA foreign_key_check").fetchall() == []
        assert (
            db.execute(
                "SELECT sql FROM sqlite_master WHERE name='trg_videos_project_limit'"
            ).fetchone()[0]
            == trigger
        )
        assert all(
            row[2] == "INTEGER"
            for row in db.execute("PRAGMA table_info(annotations)")
            if row[1] in {"x_min", "y_min", "x_max", "y_max"}
        )
    engine = make_engine(path)
    with Session(engine) as db:
        db.add_all(
            Video(
                id=f"limit-{index}",
                project_id="historical-project",
                source_type="local",
                title="limit",
            )
            for index in range(998)
        )
        db.commit()
        db.add(
            Video(
                id="too-many", project_id="historical-project", source_type="local", title="limit"
            )
        )
        with pytest.raises(IntegrityError, match="project video limit reached"):
            db.commit()
        db.rollback()
    engine.dispose()


def test_downgrade_rejects_existing_image_data(env, monkeypatch):
    imported(env)
    path = env.workspace / "db/workbench.sqlite3"
    monkeypatch.setenv("VDW_DATABASE_URL", database_url(path).render_as_string(hide_password=False))
    config = Config(str(Path(__file__).parents[1] / "alembic.ini"))
    with pytest.raises(RuntimeError, match="data will not be discarded"):
        command.downgrade(config, "0028_resource_activity_timestamps")
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageAsset.id))) == 3
        assert db.scalar(select(func.count(ImageAnnotation.id))) == 1


@pytest.mark.parametrize("method", ["hardlink", "copy"])
def test_import_worker_materialization_fallbacks_and_source_lifetime(env, monkeypatch, method):
    import vision_dataset_workbench.storage.materialize as storage

    def unavailable(*args):
        raise OSError("not supported in this fixture")

    monkeypatch.setattr(storage.fcntl, "ioctl", unavailable)
    if method == "copy":
        monkeypatch.setattr(storage.os, "link", unavailable)
    root = env.home / "source"
    source = picture(root / "one.png")
    digest = file_digest(source)
    _, images = imported(env, root, "images")
    image = images[0]
    managed = env.images.file(env.users["owner"], PROJECT, image.id)
    assert image.materialization == method
    if method == "hardlink":
        assert managed.stat().st_ino == source.stat().st_ino
        # Hardlinks share in-place source edits; only generated temporary files are touched.
        before = source.read_bytes()
        source.write_bytes(b"in-place change")
        assert managed.read_bytes() == b"in-place change"
        source.write_bytes(before)
    else:
        assert managed.stat().st_ino != source.stat().st_ino
    shutil.rmtree(root)
    assert file_digest(managed) == digest


def test_managed_media_rejects_cross_project_path_and_external_symlink(env):
    _, images = imported(env)
    image = images[0]
    original = env.workspace / image.file_path
    outside = picture(env.home / "outside.png", 77)
    original.unlink()
    original.symlink_to(outside)
    with pytest.raises(ImageNotFound):
        env.images.file(env.users["owner"], PROJECT, image.id)
    image.file_path = "../outside.png"
    with pytest.raises(ImageNotFound):
        env.images.managed_file(PROJECT, image)


def test_image_project_archive_retains_metadata_float_boxes_and_materialized_files(env):
    batch, images = imported(env)
    record, _ = ready_export(env)
    source = env.workspace / "projects" / PROJECT
    relative_files = [Path(i.file_path).relative_to(Path("projects") / PROJECT) for i in images]
    digests = {str(relative): file_digest(source / relative) for relative in relative_files}
    env.projects.delete_project(env.users["owner"], PROJECT)
    archive = env.workspace / ".deleted/projects" / PROJECT / "project"
    assert not source.exists() and archive.is_dir()
    metadata = json.loads((archive / "project_metadata.json").read_text("utf-8"))
    assert {"image_imports", "image_directories", "images", "image_annotations"} <= metadata.keys()
    assert len(metadata["image_imports"]) == 1 and metadata["image_imports"][0]["id"] == batch.id
    assert len(metadata["image_directories"]) == 3 and len(metadata["images"]) == 3
    assert {d["name"] for d in metadata["image_directories"]} == {
        "train_images",
        "val_images",
        "test_images",
    }
    assert len(metadata["image_annotations"]) == 1
    box = metadata["image_annotations"][0]
    assert isinstance(box["x_min"], float)
    assert box["x_max"] - box["x_min"] == pytest.approx(0.3)
    for relative in relative_files:
        assert file_digest(archive / relative) == digests[str(relative)]
    for image in images:
        assert (
            archive / Path(image.thumbnail_path).relative_to(Path("projects") / PROJECT)
        ).is_file()
    assert (
        archive
        / Path(record.storage_path).relative_to(Path("projects") / PROJECT)
        / "manifest.json"
    ).is_file()
    with Session(env.engine) as db:
        assert db.get(Project, PROJECT) is None
        for model in (
            ImageImport,
            ImageDirectory,
            ImageAsset,
            ImageAnnotation,
            Task,
            DatasetExport,
        ):
            assert db.scalar(select(func.count()).select_from(model)) == 0
        assert db.get(ProjectLabel, LABEL) is None
        assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []


@pytest.mark.parametrize(
    "username,status", [("owner", 201), ("editor", 201), ("viewer", 403), ("outsider", 404)]
)
def test_training_draft_consumes_image_snapshot_with_project_permissions(env, username, status):
    imported(env)
    record, _ = ready_export(env)
    client = client_for(env, username)
    response = client.post(
        "/api/v1/training-tasks",
        headers=ORIGIN,
        json={
            "code": "image-train",
            "name": "图片训练草稿",
            "default_dataset_export_id": record.id,
            "models": [{"name": "dummy model"}],
        },
    )
    assert response.status_code == status, response.text
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(TrainingTask.id))) == (1 if status == 201 else 0)
    if status == 201:
        with pytest.raises(DatasetExportConflict):
            env.exports.delete(env.users["owner"], PROJECT, record.id)


def test_training_draft_save_and_snapshot_delete_are_serialized(env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from vision_dataset_workbench.services.training import TrainingNotFound

    imported(env)
    record, _ = ready_export(env)
    client = client_for(env)
    training = client.app.state.training_service
    barrier = Barrier(2)

    def save():
        barrier.wait(timeout=5)
        try:
            task = training.create_draft(
                env.users["owner"],
                code="image-race",
                name="race",
                default_dataset_export_id=record.id,
                models=[{"name": "dummy model"}],
            )
            return "saved", task.id
        except TrainingNotFound:
            return "missing", None

    def remove():
        barrier.wait(timeout=5)
        try:
            env.exports.delete(env.users["owner"], PROJECT, record.id)
            return "deleted"
        except DatasetExportConflict:
            return "referenced"

    with ThreadPoolExecutor(max_workers=2) as pool:
        saved, removed = pool.submit(save), pool.submit(remove)
        saved, removed = saved.result(timeout=15), removed.result(timeout=15)
    assert (saved[0], removed) in {("saved", "referenced"), ("missing", "deleted")}
    with Session(env.engine) as db:
        stored = db.get(DatasetExport, record.id)
        if saved[0] == "saved":
            assert stored.deleted_at is None
            assert (env.workspace / stored.storage_path).is_dir()
            assert db.get(TrainingTask, saved[1]).default_dataset_export_id == record.id
        else:
            assert stored.deleted_at is not None
            assert db.scalar(select(func.count(TrainingTask.id))) == 0


@pytest.mark.parametrize("layout", ["roboflow", "mirror", "classes", "pure"])
def test_auto_detect_format_and_resolved_worker_import(env, layout):
    root = env.home / "auto"
    if layout == "pure":
        picture(root / "a.png")
    else:
        yolo_fixture(root, "mirror" if layout == "mirror" else "roboflow")
        if layout == "classes":
            (root / "data.yaml").unlink()
            (root / "classes.txt").write_text("object\n")
    client = client_for(env)
    base = f"/api/v1/projects/{PROJECT}/image-imports"
    preview = client.post(base + "/preview", headers=ORIGIN, json={"root_path": "auto"})
    assert preview.status_code == 200, preview.text
    preview = preview.json()
    expected = "images" if layout == "pure" else "yolo_detect"
    assert preview["format"] == expected
    result = client.post(
        base,
        headers=ORIGIN,
        json={
            "root_path": "auto",
            "fingerprint": preview["fingerprint"],
            "class_mapping": []
            if layout == "pure"
            else [{"source_id": 0, "project_label_id": LABEL}],
            "confirm_warnings": True,
        },
    )
    assert result.status_code == 202, result.text
    run_task(env, result.json()["task"]["id"])
    with Session(env.engine) as db:
        assert db.get(ImageImport, result.json()["import_id"]).format == expected
        assert db.scalar(select(func.count(ImageAnnotation.id))) == (0 if layout == "pure" else 1)


@pytest.mark.parametrize("error", ["yaml", "txt", "classes"])
def test_auto_detect_never_ignores_invalid_annotations_unless_requested(env, error):
    root = yolo_fixture(env.home / "source")
    if error == "yaml":
        (root / "data.yaml").write_text("names: [broken\n")
    elif error == "txt":
        (root / "train/labels/train.txt").write_text("0 0.5 nan 0.2 0.2")
    else:
        (root / "data.yaml").unlink()
        (root / "classes.txt").write_text("\n")
    client = client_for(env)
    base = f"/api/v1/projects/{PROJECT}/image-imports"
    preview = client.post(base + "/preview", headers=ORIGIN, json={"root_path": "source"})
    if error == "txt":
        assert preview.status_code == 200 and len(preview.json()["errors"]) == 1
        result = client.post(
            base,
            headers=ORIGIN,
            json={
                "root_path": "source",
                "fingerprint": preview.json()["fingerprint"],
                "class_mapping": [{"source_id": 0, "project_label_id": LABEL}],
            },
        )
        assert result.status_code == 422
    else:
        assert preview.status_code == 422
    payload = {"root_path": "source", "ignore_annotations": True, "format": "yolo_detect"}
    preview = client.post(base + "/preview", headers=ORIGIN, json=payload).json()
    assert preview["format"] == "images" and preview["source_classes"] == []
    assert preview["annotation_count"] == 0 and preview["errors"] == []
    result = client.post(
        base, headers=ORIGIN, json={**payload, "fingerprint": preview["fingerprint"]}
    )
    assert result.status_code == 202, result.text
    run_task(env, result.json()["task"]["id"])
    with Session(env.engine) as db:
        assert db.get(ImageImport, result.json()["import_id"]).format == "images"
        assert db.scalar(select(func.count(ImageAsset.id))) == 3
        assert db.scalar(select(func.count(ImageAnnotation.id))) == 0


def duplicate_fixture(env):
    root = env.home / "duplicates"
    first = picture(root / "a/z.png")
    (root / "b").mkdir()
    for relative in ("a/a.png", "b/b.png", "b/disabled.png"):
        shutil.copyfile(first, root / relative)
    _, images = historical_imported(env, root)
    disabled = next(i for i in images if i.file_name == "disabled.png")
    env.images.change_enabled(
        env.users["owner"], PROJECT, [{"image_id": disabled.id, "version": 1, "enabled": False}]
    )
    return images


def test_duplicate_preview_stable_keeper_and_conflict_resolution_preserves_metadata(env):
    images = duplicate_fixture(env)
    keeper = next(i for i in images if i.file_name == "a.png")
    env.images.replace(
        env.users["owner"],
        PROJECT,
        keeper.id,
        1,
        [
            dict(
                id="kept-box",
                label_id=LABEL,
                x_min=1.0,
                y_min=1.0,
                x_max=2.0,
                y_max=2.0,
                source="manual",
            )
        ],
    )
    with pytest.raises(ImageConflict, match="标注不一致"):
        env.exports.preview(env.users["owner"], PROJECT, 0.8, labels(), rules_for(env))
    preview = env.images.duplicates(env.users["owner"], PROJECT)
    assert preview == env.images.duplicates(env.users["owner"], PROJECT)
    assert preview["group_count"] == 1 and preview["duplicate_count"] == 2
    group = preview["groups"][0]
    assert group["keeper"] == {"id": keeper.id, "file_name": "a.png", "directory_name": "a"}
    assert [i["file_name"] for i in group["duplicates"]] == ["z.png", "b.png"]
    before = {i.id: (env.workspace / i.file_path).read_bytes() for i in images}
    assert env.images.disable_duplicates(env.users["owner"], PROJECT, preview["fingerprint"]) == {
        "disabled_count": 2,
        "group_count": 1,
    }
    assert env.images.duplicates(env.users["owner"], PROJECT)["groups"] == []
    record, exported = ready_export(env)
    assert exported["total_samples"] == 1 and exported["positive_samples"]["train"] == 1
    assert json.loads(record.manifest)["samples"][0]["image_id"] == keeper.id
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageAnnotation.id))) == 1
        for image in images:
            current = db.get(ImageAsset, image.id)
            assert current.enabled == (image.id == keeper.id)
            assert (env.workspace / image.file_path).read_bytes() == before[image.id]


@pytest.mark.parametrize("mutation", ["version", "annotation", "order", "enable", "new_group"])
def test_duplicate_fingerprint_rejects_stale_state_atomically(env, mutation):
    images = duplicate_fixture(env)
    old = env.images.duplicates(env.users["owner"], PROJECT)
    with Session(env.engine) as db:
        if mutation == "order":
            db.get(ImageDirectory, images[0].directory_id).sort_order = 10
        elif mutation == "new_group":
            db.get(ImageAsset, images[0].id).content_sha256 = "f" * 64
        elif mutation == "enable":
            db.get(
                ImageAsset, next(i.id for i in images if i.file_name == "disabled.png")
            ).enabled = True
        else:
            image = db.get(ImageAsset, images[0].id)
            if mutation == "version":
                image.version += 1
            else:
                image.annotation_revision += 1
        db.commit()
        before = [
            (i.id, i.enabled, i.version)
            for i in db.scalars(select(ImageAsset).order_by(ImageAsset.id))
        ]
    with pytest.raises(ImageConflict, match="重新预览"):
        env.images.disable_duplicates(env.users["owner"], PROJECT, old["fingerprint"])
    with Session(env.engine) as db:
        assert before == [
            (i.id, i.enabled, i.version)
            for i in db.scalars(select(ImageAsset).order_by(ImageAsset.id))
        ]


def test_concurrent_duplicate_submit_has_one_winner(env):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    duplicate_fixture(env)
    preview = env.images.duplicates(env.users["owner"], PROJECT)
    barrier = Barrier(2)

    def disable():
        barrier.wait(timeout=5)
        try:
            env.images.disable_duplicates(env.users["owner"], PROJECT, preview["fingerprint"])
            return "done"
        except ImageConflict:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = [pool.submit(disable) for _ in range(2)]
        assert sorted(job.result(timeout=15) for job in jobs) == ["conflict", "done"]


@pytest.mark.parametrize(
    "username,read,write",
    [("owner", 200, 200), ("editor", 200, 200), ("viewer", 200, 403), ("outsider", 404, 404)],
)
def test_new_image_api_permissions_and_responses(env, username, read, write):
    images = duplicate_fixture(env)
    client = client_for(env, username)
    base = f"/api/v1/projects/{PROJECT}/images"
    preview = client.get(base + "/duplicates")
    assert preview.status_code == read, preview.text
    owner_preview = env.images.duplicates(env.users["owner"], PROJECT)
    result = client.post(
        base + "/duplicates/disable",
        headers=ORIGIN,
        json={"fingerprint": owner_preview["fingerprint"]},
    )
    assert result.status_code == write, result.text
    if write == 200:
        assert result.json() == {"disabled_count": 2, "group_count": 1}
    disabled = next(i for i in images if i.file_name == "disabled.png")
    result = client.post(
        base + "/enabled-by-annotations",
        headers=ORIGIN,
        json={"items": [{"image_id": disabled.id, "version": 2}]},
    )
    assert result.status_code == write, result.text
    if write == 200:
        assert result.json() == {"changes": [{"id": disabled.id, "enabled": False, "version": 3}]}
    result = client.post(
        base + "/delete",
        headers=ORIGIN,
        json={"items": [{"image_id": disabled.id, "version": 3 if write == 200 else 2}]},
    )
    assert result.status_code == write, result.text
    if write == 200:
        assert result.json() == {"deleted": [disabled.id]}


def test_image_empty_api_save_and_removed_confirm_endpoint(env):
    _, images = imported(env)
    client = client_for(env)
    base = f"/api/v1/projects/{PROJECT}/images"
    positive = next(i for i in images if i.file_name == "train.png")
    result = client.put(
        base + f"/{positive.id}/annotations",
        headers=ORIGIN,
        json={"annotation_revision": 1, "items": []},
    )
    assert result.status_code == 200, result.text
    assert result.json()["items"] == [] and result.json()["annotation_revision"] == 2
    assert client.post(
        base + "/confirm-negative", headers=ORIGIN, json={"items": []}
    ).status_code in {404, 405}
    assert not hasattr(env.images, "confirm_negative")


@pytest.mark.parametrize("endpoint", ["delete", "enabled-by-annotations", "duplicates/disable"])
def test_new_api_origin_schema_and_scope_guards(env, endpoint):
    _, images = imported(env)
    client = client_for(env)
    base = f"/api/v1/projects/{PROJECT}/images/"
    payload = (
        {"fingerprint": "0" * 64}
        if endpoint == "duplicates/disable"
        else {"items": [{"image_id": images[0].id, "version": 1}]}
    )
    assert (
        client.post(
            base + endpoint, headers={"Origin": "http://evil.example"}, json=payload
        ).status_code
        == 403
    )
    invalid = {"fingerprint": "invalid"} if endpoint == "duplicates/disable" else {"items": []}
    assert client.post(base + endpoint, headers=ORIGIN, json=invalid).status_code == 422
    assert (
        client.post(
            "/api/v1/projects/video-project/images/" + endpoint, headers=ORIGIN, json=payload
        ).status_code
        == 422
    )
    if endpoint != "duplicates/disable":
        assert (
            client.post(
                "/api/v1/projects/other-project/images/" + endpoint, headers=ORIGIN, json=payload
            ).status_code
            == 404
        )
        invalid = {"items": [{"image_id": images[0].id, "version": 0}]}
        assert client.post(base + endpoint, headers=ORIGIN, json=invalid).status_code == 422


def test_enabled_by_annotations_uses_actual_boxes_and_is_atomic(env):
    _, images = imported(env)
    positive = next(i for i in images if i.file_name == "train.png")
    env.images.change_enabled(
        env.users["owner"], PROJECT, [{"image_id": positive.id, "version": 1, "enabled": False}]
    )
    items = [{"image_id": i.id, "version": 2 if i.id == positive.id else 1} for i in images]
    with pytest.raises(ImageConflict):
        env.images.change_enabled(
            env.users["owner"],
            PROJECT,
            [items[0], {**items[1], "version": 99}],
            by_annotations=True,
        )
    with pytest.raises(ValueError, match="duplicate"):
        env.images.change_enabled(
            env.users["owner"], PROJECT, [items[0], items[0]], by_annotations=True
        )
    current = env.images.change_enabled(env.users["owner"], PROJECT, items, by_annotations=True)
    assert {i.id for i in current if i.enabled} == {positive.id}
    assert all(i.annotation_revision == 1 for i in current)
    assert {i.id: i.version for i in current} == {i["image_id"]: i["version"] + 1 for i in items}


def test_delete_archives_float_annotations_and_keeps_existing_export(env):
    _, images = imported(env)
    record, _ = ready_export(env)
    export_root = env.workspace / record.storage_path
    exported = {
        str(p.relative_to(export_root)): p.read_bytes()
        for p in export_root.rglob("*")
        if p.is_file()
    }
    versions = env.images.change_enabled(
        env.users["owner"],
        PROJECT,
        [{"image_id": i.id, "version": 1, "enabled": False} for i in images],
    )
    assert env.images.delete(
        env.users["owner"], PROJECT, [{"image_id": i.id, "version": i.version} for i in versions]
    ) == {"deleted": [i.id for i in versions]}
    for image in images:
        archive = env.workspace / ".deleted/projects" / PROJECT / "images" / image.id
        metadata = json.loads((archive / "metadata.json").read_text())
        assert metadata["image"]["content_sha256"] == image.content_sha256
        for field in ("file_path", "thumbnail_path"):
            relative = Path(getattr(image, field)).relative_to(
                Path("projects") / PROJECT / "images"
            )
            assert (archive / relative).is_file()
            assert not (env.workspace / getattr(image, field)).exists()
        if image.file_name == "train.png":
            box = metadata["annotations"][0]
            assert box["x_max"] - box["x_min"] == pytest.approx(0.3)
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageAsset.id))) == 0
        assert db.scalar(select(func.count(ImageAnnotation.id))) == 0
        assert db.get(DatasetExport, record.id).manifest == record.manifest
        assert db.connection().exec_driver_sql("PRAGMA foreign_key_check").all() == []
    assert exported == {
        str(p.relative_to(export_root)): p.read_bytes()
        for p in export_root.rglob("*")
        if p.is_file()
    }
    assert env.exports.download_directory(env.users["owner"], PROJECT, record.id)[1] == export_root


@pytest.mark.parametrize(
    "failure",
    ["enabled", "stale", "duplicate", "unknown", "archive_exists", "move", "metadata", "commit"],
)
def test_delete_batch_rolls_back_files_and_database(env, monkeypatch, failure):
    from sqlalchemy import event
    import vision_dataset_workbench.services.images as implementation

    _, images = imported(env)
    env.images.change_enabled(
        env.users["owner"],
        PROJECT,
        [{"image_id": i.id, "version": 1, "enabled": False} for i in images],
    )
    items = [{"image_id": i.id, "version": 2} for i in images]
    paths = [env.workspace / getattr(i, f) for i in images for f in ("file_path", "thumbnail_path")]
    contents = [p.read_bytes() for p in paths]
    with Session(env.engine) as db:
        stamp = db.get(Project, PROJECT).updated_at
    if failure == "enabled":
        with Session(env.engine) as db:
            db.get(ImageAsset, images[-1].id).enabled = True
            db.commit()
    elif failure == "stale":
        items[-1]["version"] = 99
    elif failure == "duplicate":
        items.append(items[0])
    elif failure == "unknown":
        items[-1]["image_id"] = "unknown"
    elif failure == "archive_exists":
        (env.workspace / ".deleted/projects" / PROJECT / "images" / images[-1].id).mkdir(
            parents=True
        )
    elif failure == "move":
        original = implementation.os.replace
        calls = 0

        def fail_one(source, target):
            nonlocal calls
            calls += 1
            if calls == 3:
                raise OSError("injected move failure")
            return original(source, target)

        monkeypatch.setattr(implementation.os, "replace", fail_one)
    elif failure == "metadata":
        original = Path.write_text

        def fail_metadata(path, *args, **kwargs):
            if path.name == "metadata.json":
                raise OSError("injected metadata failure")
            return original(path, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", fail_metadata)
    else:

        def fail_commit(db):
            raise OSError("injected commit failure")

        event.listen(env.images._session_factory, "before_commit", fail_commit)
    try:
        with pytest.raises((ValueError, OSError)):
            env.images.delete(env.users["owner"], PROJECT, items)
    finally:
        if failure == "commit":
            event.remove(env.images._session_factory, "before_commit", fail_commit)
    assert [p.read_bytes() for p in paths] == contents
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageAsset.id))) == 3
        assert db.scalar(select(func.count(ImageAnnotation.id))) == 1
        assert all(i.version == 2 for i in db.scalars(select(ImageAsset)))
        assert db.get(Project, PROJECT).updated_at == stamp
    archived = list((env.workspace / ".deleted").rglob("metadata.json"))
    assert archived == []


@pytest.mark.parametrize(
    "escape",
    [
        "external_file",
        "external_parent",
        "other_project",
        "archive_symlink",
        "absolute",
        "traversal",
    ],
)
def test_delete_rejects_unsafe_paths_without_touching_sources(env, escape):
    _, images = imported(env)
    image = images[0]
    env.images.change_enabled(
        env.users["owner"], PROJECT, [{"image_id": image.id, "version": 1, "enabled": False}]
    )
    outside = picture(env.home / "outside.png", 44)
    before = outside.read_bytes()
    path = env.workspace / image.file_path
    if escape == "external_file":
        path.unlink()
        path.symlink_to(outside)
    elif escape == "external_parent":
        folder = path.parent
        moved = folder.with_name(folder.name + "_saved")
        folder.rename(moved)
        folder.symlink_to(moved, target_is_directory=True)
    elif escape == "archive_symlink":
        (env.workspace / ".deleted").symlink_to(env.home, target_is_directory=True)
    elif escape in {"absolute", "traversal"}:
        with Session(env.engine) as db:
            db.get(ImageAsset, image.id).file_path = (
                str(path)
                if escape == "absolute"
                else str(Path(image.file_path).parent / "unused" / ".." / path.name)
            )
            db.commit()
    else:
        with Session(env.engine) as db:
            db.get(ImageAsset, image.id).file_path = "projects/other-project/images/outside.png"
            db.commit()
    with pytest.raises(ValueError):
        env.images.delete(env.users["owner"], PROJECT, [{"image_id": image.id, "version": 2}])
    assert outside.read_bytes() == before
    with Session(env.engine) as db:
        assert db.get(ImageAsset, image.id) is not None


@pytest.mark.parametrize(
    "positives,negatives,ratio",
    [
        (2, 2, 0.8),
        (2, 0, 0.99),
        (0, 2, 0.01),
        (1, 1, 0.8),
        (3, 3, 0.5),
        (4, 5, 0.0),
        (4, 5, 1.0),
        (7, 9, 0.6),
    ],
)
def test_stratified_directory_ratios_and_real_worker_labels(env, positives, negatives, ratio):
    root = env.home / "strata"
    for directory in ("first", "second"):
        for n in range(positives + negatives):
            picture(
                root / directory / f"{n:03}.png",
                n + (100 if directory == "second" else 0),
                size=(8, 8),
            )
    _, images = imported(env, root, "images")
    for image in images:
        if int(Path(image.file_name).stem) < positives:
            env.images.replace(
                env.users["owner"],
                PROJECT,
                image.id,
                1,
                [
                    dict(
                        id="box-" + image.id[:20],
                        label_id=LABEL,
                        x_min=0.1,
                        y_min=0.1,
                        x_max=2.0,
                        y_max=2.0,
                        source="manual",
                    )
                ],
            )
    rules = rules_for(env)
    # The second directory uses its own ratio rather than the global value.
    second = next(
        d for d in env.images.directories(env.users["owner"], PROJECT) if d["name"] == "second"
    )
    next(r for r in rules if r["directory_id"] == second["id"])["train_ratio"] = 0.5
    record, preview = ready_export(env, rules, ratio=ratio)
    manifest = json.loads(record.manifest)
    for stat in preview["directory_stats"]:
        r = 0.5 if stat["name"] == "second" else ratio
        for kind, total in (("positive", positives), ("negative", negatives)):
            expected = target_train_count(total, r)
            assert stat[kind + "_images"] == total
            assert stat["train_" + kind + "_images"] == expected
            assert stat["val_" + kind + "_images"] == total - expected
            assert stat[kind + "_deviation"] == 0
    export_root = env.workspace / record.storage_path
    for kind in ("positive", "negative"):
        assert preview[kind + "_samples"] == manifest[kind + "_samples"]
        assert sum(preview[kind + "_samples"].values()) == 2 * (
            positives if kind == "positive" else negatives
        )
    for sample in manifest["samples"]:
        text = (
            export_root / sample["split"] / "labels" / (Path(sample["output_name"]).stem + ".txt")
        ).read_text()
        assert bool(text) == sample["positive"]
    assert not (
        {s["content_sha256"] for s in manifest["samples"] if s["split"] == "train"}
        & {s["content_sha256"] for s in manifest["samples"] if s["split"] == "val"}
    )


def test_export_class_selection_defines_positive_negative_and_fingerprint(env):
    _, images = imported(env)
    from vision_dataset_workbench.services.labels import LabelService

    second = LabelService(env.engine, env.projects).create_label(
        env.users["owner"], PROJECT, "second", "", "#16866f"
    )
    image = next(i for i in images if i.file_name == "test.png")
    env.images.replace(
        env.users["owner"],
        PROJECT,
        image.id,
        1,
        [
            dict(
                id="second-box",
                label_id=second.id,
                x_min=1.0,
                y_min=1.0,
                x_max=2.0,
                y_max=2.0,
                source="manual",
            )
        ],
    )
    selected = [
        ExportLabelInput(LABEL, "object", 0, False),
        ExportLabelInput(second.id, "second", 1, True),
    ]
    rules = rules_for(env)
    preview = env.exports.preview(env.users["owner"], PROJECT, 0.8, selected, rules)
    assert sum(preview["positive_samples"].values()) == 1
    assert sum(preview["negative_samples"].values()) == 2
    assert preview["filtered_annotations"] == 1
    changed = [
        ExportLabelInput(LABEL, "object", 0, True),
        ExportLabelInput(second.id, "second", 1, True),
    ]
    with pytest.raises(DatasetExportConflict, match="重新预览"):
        env.exports.create(
            env.users["owner"],
            PROJECT,
            "changed",
            0.8,
            changed,
            directory_rules=rules,
            preview_fingerprint=preview["fingerprint"],
        )
    record = env.exports.create(
        env.users["owner"],
        PROJECT,
        "selected",
        0.8,
        selected,
        directory_rules=rules,
        preview_fingerprint=preview["fingerprint"],
    )
    run_task(env, record.task_id)
    record = env.exports.get(env.users["owner"], PROJECT, record.id)
    manifest = json.loads(record.manifest)
    assert manifest["positive_samples"] == preview["positive_samples"]
    assert manifest["negative_samples"] == preview["negative_samples"]
    root = env.workspace / record.storage_path
    texts = [p.read_text() for p in root.glob("*/labels/*.txt")]
    assert len(texts) == 3 and sum(bool(t) for t in texts) == 1
    assert next(t for t in texts if t).startswith("1 ")


def test_pinned_hash_group_overrides_ratio_and_reports_stratum_deviation(env):
    root = env.home / "pinned"
    first = picture(root / "fixed/one.png")
    (root / "ratio").mkdir()
    shutil.copyfile(first, root / "ratio/duplicate.png")
    picture(root / "ratio/unique.png", 42)
    _, images = historical_imported(env, root)
    # Annotation status alone is irrelevant to an empty exported label file.
    env.images.replace(env.users["owner"], PROJECT, images[0].id, 1, [])
    rules = rules_for(env, {"fixed": "train"})
    next(r for r in rules if r["mode"] == "ratio")["train_ratio"] = 0.0
    record, preview = ready_export(env, rules)
    manifest = json.loads(record.manifest)
    assert (
        len({s["split"] for s in manifest["samples"] if s["content_sha256"] == file_digest(first)})
        == 1
    )
    ratio_stat = next(s for s in preview["directory_stats"] if s["name"] == "ratio")
    assert ratio_stat["train_negative_images"] == 1 and ratio_stat["val_negative_images"] == 1
    assert ratio_stat["negative_deviation"] == 1 and ratio_stat["deviation_reason"]


def test_preview_excludes_disabled_unavailable_and_unselected_directory(env):
    _, images = imported(env)
    disabled, missing, excluded = images
    env.images.change_enabled(
        env.users["owner"], PROJECT, [{"image_id": disabled.id, "version": 1, "enabled": False}]
    )
    (env.workspace / missing.file_path).unlink()
    rules = rules_for(env)
    next(r for r in rules if r["directory_id"] == excluded.directory_id)["included"] = False
    preview = env.exports.preview(env.users["owner"], PROJECT, 0.8, labels(), rules)
    assert preview["total_samples"] == 0
    assert preview["excluded"] == {"disabled": 1, "file_unavailable": 1, "directory_excluded": 1}
    assert preview["positive_samples"] == preview["negative_samples"] == {"train": 0, "val": 0}


@pytest.mark.parametrize(
    "count,ratio,reason",
    [
        (1, 0.8, "insufficient_samples"),
        (2, 0.8, "exact_content_groups"),
        (3, 0.5, "exact_content_groups"),
    ],
)
def test_unsplittable_small_strata_report_limits(env, count, ratio, reason):
    root = env.home / "small"
    first = picture(root / "0.png")
    for n in range(1, count):
        shutil.copyfile(first, root / f"{n}.png")
    historical_imported(env, root)
    preview = env.exports.preview(env.users["owner"], PROJECT, ratio, labels(), rules_for(env))
    stat = preview["directory_stats"][0]
    assert stat["negative_images"] == count
    assert stat["negative_deviation_reason"] == reason
    assert preview["stratification_warnings"] == [
        {"directory_id": stat["directory_id"], "kind": "negative", "reason": reason}
    ]
    assert stat["train_negative_images"] in {0, count}
    assert stat["negative_deviation"] == stat["train_negative_images"] - target_train_count(
        count, ratio
    )


@pytest.mark.parametrize("image_directory", ["images", "train/images"])
@pytest.mark.parametrize("format", [None, "auto"])
def test_auto_detect_unconfigured_image_tree_scans_all_images(tmp_path, image_directory, format):
    root = tmp_path / "source"
    picture(root / image_directory / "a.png")
    picture(root / "other/b.png", 1)
    scan = scan_images(root, format)
    assert scan.format == "images" and not scan.warnings and not scan.errors
    assert len(scan.images) == scan.preview()["total_images"] == 2
    assert {i["path"] for i in scan.images} == {f"{image_directory}/a.png", "other/b.png"}


@pytest.mark.parametrize("layout", ["roboflow", "mirror"])
def test_auto_detect_labels_without_configuration_preserves_yolo_validation(tmp_path, layout):
    root = yolo_fixture(tmp_path / "source", layout)
    (root / "data.yaml").unlink()
    # Keep two images, with only labels-tree evidence for automatic YOLO detection.
    image_directory = "test/images" if layout == "roboflow" else "images/test"
    (root / image_directory / "test.png").unlink()
    scan = scan_images(root)
    assert scan.format == "yolo_detect" and not scan.errors
    assert len(scan.images) == scan.preview()["total_images"] == 2
    assert len(scan.images[0]["annotations"]) + len(scan.images[1]["annotations"]) == 1
    label = root / ("train/labels/train.txt" if layout == "roboflow" else "labels/train/train.txt")
    label.write_text("0 0.5 nan 0.2 0.2")
    invalid = scan_images(root)
    assert invalid.format == "yolo_detect" and len(invalid.errors) == 1
    assert "归一化" in invalid.errors[0]["message"] or "有限" in invalid.errors[0]["message"]


def test_delete_unavailable_file_retains_missing_metadata(env):
    _, images = imported(env)
    image = images[0]
    (env.workspace / image.file_path).unlink()
    env.images.change_enabled(
        env.users["owner"], PROJECT, [{"image_id": image.id, "version": 1, "enabled": False}]
    )
    env.images.delete(env.users["owner"], PROJECT, [{"image_id": image.id, "version": 2}])
    archive = env.workspace / ".deleted/projects" / PROJECT / "images" / image.id
    metadata = json.loads((archive / "metadata.json").read_text())
    assert metadata["missing"] == [image.file_path]
    assert metadata["image"]["id"] == image.id


def test_independent_hash_groups_reach_attainable_stratified_target(env):
    root = env.home / "weighted"
    for index, count in enumerate((8, 7, 6, 5)):
        first = picture(root / f"{index}-0.png", index)
        for n in range(1, count):
            shutil.copyfile(first, root / f"{index}-{n}.png")
    historical_imported(env, root)
    for seed in range(12):
        preview = env.exports.preview(
            env.users["owner"], PROJECT, 0.5, labels(), rules_for(env), seed
        )
        assert preview["negative_samples"] == {"train": 13, "val": 13}, seed


@pytest.mark.parametrize("operation", ["enabled_by_annotations", "disable_duplicates"])
def test_new_bulk_operations_rollback_on_database_failure(env, operation):
    from sqlalchemy import event

    images = duplicate_fixture(env)
    with Session(env.engine) as db:
        before = [
            (i.id, i.enabled, i.version)
            for i in db.scalars(select(ImageAsset).order_by(ImageAsset.id))
        ]
        stamp = db.get(Project, PROJECT).updated_at
    preview = env.images.duplicates(env.users["owner"], PROJECT)

    def fail_commit(db):
        raise OSError("injected commit failure")

    event.listen(env.images._session_factory, "before_commit", fail_commit)
    try:
        with pytest.raises(OSError, match="injected"):
            if operation == "disable_duplicates":
                env.images.disable_duplicates(env.users["owner"], PROJECT, preview["fingerprint"])
            else:
                env.images.change_enabled(
                    env.users["owner"],
                    PROJECT,
                    [
                        {"image_id": i.id, "version": 2 if i.file_name == "disabled.png" else 1}
                        for i in images
                    ],
                    by_annotations=True,
                )
    finally:
        event.remove(env.images._session_factory, "before_commit", fail_commit)
    with Session(env.engine) as db:
        assert before == [
            (i.id, i.enabled, i.version)
            for i in db.scalars(select(ImageAsset).order_by(ImageAsset.id))
        ]
        assert db.get(Project, PROJECT).updated_at == stamp


def test_enabled_by_annotations_ignores_pending_status_if_boxes_exist(env):
    _, images = imported(env)
    positive = next(i for i in images if i.file_name == "train.png")
    with Session(env.engine) as db:
        image = db.get(ImageAsset, positive.id)
        image.enabled, image.annotation_status = False, "pending"
        db.commit()
    [image] = env.images.change_enabled(
        env.users["owner"], PROJECT, [{"image_id": positive.id, "version": 1}], by_annotations=True
    )
    assert image.enabled and image.annotation_status == "pending" and image.annotation_revision == 1


def test_screening_saves_over_200_changes_atomically_and_rolls_back_stale_tail(env):
    root = env.home / "screening-205"
    for index in range(205):
        picture(root / f"{index:03d}.png", index, size=(8, 8))
    imported(env, root, "images")
    with Session(env.engine) as db:
        images = list(
            db.scalars(
                select(ImageAsset).join(ImageDirectory).where(ImageDirectory.project_id == PROJECT)
            )
        )
    changes = [{"image_id": image.id, "version": 1, "enabled": False} for image in images]
    assert len(changes) == 205
    client = client_for(env)
    url = f"/api/v1/projects/{PROJECT}/images/enabled"
    stale = [dict(change) for change in changes]
    stale[-1]["version"] = 2
    response = client.post(url, headers=ORIGIN, json={"changes": stale})
    assert response.status_code == 409, response.text
    with Session(env.engine) as db:
        rows = list(
            db.scalars(
                select(ImageAsset).join(ImageDirectory).where(ImageDirectory.project_id == PROJECT)
            )
        )
        assert len(rows) == 205
        assert all(image.enabled and image.version == 1 for image in rows)
    response = client.post(url, headers=ORIGIN, json={"changes": changes})
    assert response.status_code == 200, response.text
    assert len(response.json()) == 205
    with Session(env.engine) as db:
        rows = list(
            db.scalars(
                select(ImageAsset).join(ImageDirectory).where(ImageDirectory.project_id == PROJECT)
            )
        )
        assert all(not image.enabled and image.version == 2 for image in rows)


def test_import_deduplicates_batch_before_mapping_and_creates_no_empty_directory(env):
    root = env.home / "dedup"
    first = picture(root / "train/images/a.png")
    (root / "train/labels").mkdir(parents=True)
    (root / "train/labels/a.txt").write_text("0 0.5 0.5 0.2 0.2")
    (root / "val/images").mkdir(parents=True)
    (root / "val/labels").mkdir(parents=True)
    shutil.copyfile(first, root / "val/images/b.png")
    (root / "val/labels/b.txt").write_text("1 0.5 0.5 0.4 0.4")
    (root / "data.yaml").write_text(
        yaml.safe_dump(
            {"train": "train/images", "val": "val/images", "names": ["object", "unused"]}
        )
    )
    preview = env.images.preview(env.users["owner"], PROJECT, "dedup")
    assert {
        k: preview[k] for k in ("total_images", "new_images", "existing_images", "duplicate_images")
    } == {"total_images": 2, "new_images": 1, "existing_images": 0, "duplicate_images": 1}
    assert preview["source_classes"] == [{"source_id": 0, "name": "object"}]
    batch, task = submit_import(env, root, None)
    result = json.loads(run_task(env, task.id))
    assert result["images"] == result["new_images"] == result["duplicate_images"] == 1
    assert len(result["image_ids"]) == 1
    directories = env.images.directories(env.users["owner"], PROJECT)
    assert len(directories) == 1 and directories[0]["name"] == "train_images"
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageAsset.id))) == 1
        assert db.scalar(select(func.count(ImageAnnotation.id))) == 1
        assert (
            db.scalar(select(func.count(ProjectLabel.id)).where(ProjectLabel.project_id == PROJECT))
            == 1
        )
        assert db.get(ImageImport, batch.id).status == "ready"


def test_incremental_import_reuses_directories_preserves_annotations_and_disabled_images(env):
    root = yolo_fixture(env.home / "source")
    _, images = imported(env, root)
    train = next(i for i in images if i.file_name == "train.png")
    env.images.change_enabled(
        env.users["owner"], PROJECT, [{"image_id": train.id, "version": 1, "enabled": False}]
    )
    before = env.images.get(env.users["owner"], PROJECT, train.id)
    old_directories = env.images.directories(env.users["owner"], PROJECT)
    (root / "train/labels/train.txt").write_text("0 0.4 0.4 0.1 0.1")
    # All duplicates creates neither a task, a batch nor an unused new class.
    preview = env.images.preview(env.users["owner"], PROJECT, "source")
    assert preview["new_images"] == 0 and preview["existing_images"] == 3
    assert preview["source_classes"] == []
    with pytest.raises(ValueError, match="没有可新增"):
        env.images.create_import(
            env.users["owner"],
            PROJECT,
            "source",
            None,
            preview["fingerprint"],
            [{"source_id": 0, "new_label_name": "unused"}],
            True,
        )
    picture(root / "train/images/added.png", 83)
    (root / "train/labels/added.txt").write_text("0 0.5 0.5 0.3 0.3")
    picture(root / "val/images/added.png", 84)
    (root / "val/labels/added.txt").write_text("")
    preview = env.images.preview(env.users["owner"], PROJECT, "source")
    assert (preview["total_images"], preview["new_images"], preview["existing_images"]) == (5, 2, 3)
    batch, task = submit_import(env, root, None)
    result = json.loads(run_task(env, task.id))
    assert result["images"] == 2
    assert {d["id"] for d in env.images.directories(env.users["owner"], PROJECT)} == {
        d["id"] for d in old_directories
    }
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageImport.id))) == 2
        assert db.scalar(select(func.count(Task.id))) == 2
        assert db.scalar(select(func.count(ImageAsset.id))) == 5
        assert (
            db.scalar(
                select(func.count(ImageDirectory.id)).where(ImageDirectory.import_id == batch.id)
            )
            == 0
        )
    after = env.images.get(env.users["owner"], PROJECT, train.id)
    assert (after[0].enabled, after[0].version, after[0].annotation_revision) == (False, 2, 1)
    assert [(a.id, a.x_min, a.x_max) for a in before[1]] == [
        (a.id, a.x_min, a.x_max) for a in after[1]
    ]


@pytest.mark.parametrize("child_first", [False, True])
def test_incremental_import_matches_full_home_source_directory_across_root_choices(
    env, child_first
):
    root = env.home / "sources/a"
    child = root / "train/images"
    picture(child / "first.png", 10)
    _, images = imported(env, child if child_first else root, "images")
    directory_id = images[0].directory_id
    picture(child / "second.png", 11)
    _, task = submit_import(env, root if child_first else child, "images")
    run_task(env, task.id)
    items, _, total, _ = env.images.list_images(env.users["owner"], PROJECT)
    assert total == 2 and {i.directory_id for i in items} == {directory_id}
    added = next(i for i in items if i.file_name == "second.png")
    assert added.source_relative_path == (
        "second.png" if child_first else "train/images/second.png"
    )
    # Same relative directory under another root must not be merged.
    other = env.home / "sources/b"
    picture(other / "train/images/third.png", 12)
    _, task = submit_import(env, other, "images")
    run_task(env, task.id)
    assert len(env.images.directories(env.users["owner"], PROJECT)) == 2


def test_same_content_other_root_skips_and_deleted_asset_can_be_imported_again(env):
    root = env.home / "first"
    first = picture(root / "one.png")
    _, [image] = imported(env, root, "images")
    target = env.home / "second"
    target.mkdir()
    shutil.copyfile(first, target / "different-name.png")
    preview = env.images.preview(env.users["owner"], PROJECT, "second")
    assert preview["existing_images"] == 1 and preview["new_images"] == 0
    env.images.change_enabled(
        env.users["owner"], PROJECT, [{"image_id": image.id, "version": 1, "enabled": False}]
    )
    env.images.delete(env.users["owner"], PROJECT, [{"image_id": image.id, "version": 2}])
    _, task = submit_import(env, root, "images")
    run_task(env, task.id)
    new = env.images.list_images(env.users["owner"], PROJECT)[0]
    assert len(new) == 1 and new[0].id != image.id


def test_changed_bytes_at_existing_source_path_requires_rename_without_overwriting(env):
    root = env.home / "source"
    path = picture(root / "one.png")
    _, [image] = imported(env, root, "images")
    old_hash = image.content_sha256
    # Replace the source inode so hardlink fallback cannot modify the managed original.
    path.unlink()
    picture(path, 99)
    preview = env.images.preview(env.users["owner"], PROJECT, "source")
    assert "已有不同内容" in preview["errors"][0]["message"]
    with pytest.raises(ValueError, match="来源存在错误"):
        env.images.create_import(
            env.users["owner"], PROJECT, "source", None, preview["fingerprint"], [], True
        )
    assert env.images.get(env.users["owner"], PROJECT, image.id)[0].content_sha256 == old_hash


@pytest.mark.parametrize("phase", ["preview", "create_lock", "worker_scan", "worker_publish"])
def test_import_project_asset_set_cas_rejects_changes_atomically(env, monkeypatch, phase):
    _, images = imported(env)
    root = env.home / "increment"
    picture(root / "added.png", 72)
    preview = env.images.preview(env.users["owner"], PROJECT, "increment")

    def mutate():
        with Session(env.engine) as db:
            db.get(ImageAsset, images[0].id).content_sha256 = "a" * 64
            db.commit()

    if phase == "preview":
        mutate()
    elif phase == "create_lock":
        original = env.images._scan

        def changed(*args, **kwargs):
            result = original(*args, **kwargs)
            mutate()
            return result

        monkeypatch.setattr(env.images, "_scan", changed)
    if phase in {"preview", "create_lock"}:
        with pytest.raises(ImageConflict, match="已变化"):
            env.images.create_import(
                env.users["owner"], PROJECT, "increment", "images", preview["fingerprint"], [], True
            )
    else:
        batch, task = submit_import(env, root, "images")
        if phase == "worker_scan":
            mutate()
        else:
            original = env.worker._heartbeat

            def changed(task_id, progress):
                original(task_id, progress)
                if progress >= 95:
                    mutate()

            monkeypatch.setattr(env.worker, "_heartbeat", changed)
        run_task(env, task.id, "failed")
        assert not (env.workspace / "projects" / PROJECT / "images" / batch.id).exists()
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageAsset.id))) == 3
        assert db.scalar(select(func.count(ImageDirectory.id))) == 3
        assert db.scalar(select(func.count(Task.id))) == (
            1 if phase in {"preview", "create_lock"} else 2
        )


@pytest.mark.parametrize(
    "legacy_result,missing_new_file", [(False, False), (True, False), (False, True), (True, True)]
)
def test_incremental_ready_retry_checks_exact_batch_assets_without_directory_import_id(
    env, legacy_result, missing_new_file
):
    root = env.home / "source"
    picture(root / "old.png", 10)
    imported(env, root, "images")
    picture(root / "new.png", 11)
    batch, task = submit_import(env, root, "images")
    result = json.loads(run_task(env, task.id))
    shutil.rmtree(root)
    with Session(env.engine) as db:
        assert (
            db.scalar(
                select(func.count(ImageDirectory.id)).where(ImageDirectory.import_id == batch.id)
            )
            == 0
        )
        added = db.get(ImageAsset, result["image_ids"][0])
        if missing_new_file:
            (env.workspace / added.file_path).unlink()
        old = db.get(Task, task.id)
        if legacy_result:
            result.pop("image_ids")
            old.result = json.dumps(result)
        old.status, old.lease_owner = "running", "dead-worker"
        old.lease_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=5
        )
        db.commit()
    run_task(env, task.id, "failed" if missing_new_file else "succeeded")
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageAsset.id))) == 2
        assert db.scalar(select(func.count(ImageDirectory.id))) == 1
        assert db.get(ImageImport, batch.id).status == "ready"


def test_list_images_multiple_directory_filters_and_summary_cover_full_filtered_range(env):
    root = env.home / "many"
    for index in range(76):
        picture(root / ("a" if index < 65 else "b") / f"match-{index:02}.png", index, size=(8, 8))
    imported(env, root, "images")
    with Session(env.engine) as db:
        for index, image in enumerate(
            db.scalars(select(ImageAsset).order_by(ImageAsset.file_name))
        ):
            image.enabled = index % 2 == 0
            image.annotation_status = "labeled" if index % 3 == 0 else "pending"
        db.commit()
    directories = env.images.directories(env.users["owner"], PROJECT)
    first_id, second_id = [d["id"] for d in directories]
    client = client_for(env)
    url = f"/api/v1/projects/{PROJECT}/images"
    response = client.get(url, params=[("directory_id", first_id), ("directory_id", second_id)])
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["items"]) == 50 and payload["total"] == 76
    assert payload["summary"] == {"enabled_images": 38, "labeled_images": 26}
    response = client.get(
        url,
        params={
            "directory_id": first_id,
            "enabled": "true",
            "annotation_status": "labeled",
            "search": "match",
        },
    )
    assert response.status_code == 200
    assert response.json()["total"] == 11
    assert response.json()["summary"] == {"enabled_images": 11, "labeled_images": 11}
    none = client.get(url, params={"directory_id": "missing"}).json()
    assert none["total"] == 0 and none["summary"] == {"enabled_images": 0, "labeled_images": 0}
    # Service-level legacy string callers and filtered neighbors retain the same ordering.
    items, _, total, summary = env.images.list_images(
        env.users["owner"], PROJECT, directory_id=first_id
    )
    assert total == 65 and summary == {"enabled_images": 33, "labeled_images": 22}
    neighbors = client.get(
        f"{url}/{items[0].id}/neighbors",
        params=[("directory_id", first_id), ("directory_id", second_id)],
    ).json()
    assert neighbors["previous_id"] is None and neighbors["next_id"] == items[1].id


@pytest.mark.parametrize("operation", ["cancel", "publish_failure", "lease_lost", "commit"])
def test_incremental_import_failure_does_not_change_reused_directory_or_labels(
    env, monkeypatch, operation
):
    root = yolo_fixture(env.home / "source")
    _, images = imported(env, root)
    before_directories = env.images.directories(env.users["owner"], PROJECT)
    picture(root / "train/images/added.png", 91)
    (root / "train/labels/added.txt").write_text("0 0.5 0.5 0.2 0.2")
    batch, task = submit_import(
        env, root, mappings=[{"source_id": 0, "new_label_name": "must_rollback"}]
    )
    if operation == "publish_failure":
        import vision_dataset_workbench.image_import_task as implementation

        def fail(*args):
            raise OSError("publication failed")

        monkeypatch.setattr(implementation.os, "replace", fail)
    elif operation == "commit":
        from sqlalchemy import event

        def fail_commit(db):
            if db.get(ImageImport, batch.id).status == "ready":
                raise ValueError("publication commit failed")

        event.listen(env.worker._session_factory, "before_commit", fail_commit)
    else:
        original = env.worker._heartbeat

        def interrupt(task_id, progress):
            original(task_id, progress)
            if progress >= 95:
                with Session(env.engine) as db:
                    stored = db.get(Task, task_id)
                    if operation == "cancel":
                        stored.cancel_requested = True
                    else:
                        stored.lease_owner = "replacement-worker"
                    db.commit()

        monkeypatch.setattr(env.worker, "_heartbeat", interrupt)
    try:
        run_task(
            env, task.id, {"cancel": "canceled", "lease_lost": "running"}.get(operation, "failed")
        )
    finally:
        if operation == "commit":
            event.remove(env.worker._session_factory, "before_commit", fail_commit)
    assert env.images.directories(env.users["owner"], PROJECT) == before_directories
    with Session(env.engine) as db:
        assert set(db.scalars(select(ImageAsset.id))) == {i.id for i in images}
        assert db.scalar(select(func.count(ImageAnnotation.id))) == 1
        assert (
            db.scalar(select(func.count(ProjectLabel.id)).where(ProjectLabel.project_id == PROJECT))
            == 1
        )
    assert not (env.workspace / "projects" / PROJECT / "images" / batch.id).exists()
    assert not list((env.workspace / "tmp").iterdir())


def test_hash_deduplication_is_project_scoped(env):
    root = env.home / "shared-source"
    picture(root / "one.png")
    preview = env.images.preview(env.users["owner"], "other-project", "shared-source")
    _, task = env.images.create_import(
        env.users["owner"], "other-project", "shared-source", None, preview["fingerprint"], [], True
    )
    run_task(env, task.id)
    _, [image] = imported(env, root, "images")
    assert image.content_sha256 == file_digest(root / "one.png")
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageAsset.id))) == 2


@pytest.mark.parametrize("incremental", [False, True])
def test_queued_legacy_import_without_project_fingerprint_still_recovers(env, incremental):
    root = yolo_fixture(env.home / "source")
    if incremental:
        imported(env, root)
        picture(root / "train/images/added.png", 91)
    used_names = {d["name"] for d in env.images.directories(env.users["owner"], PROJECT)}
    batch, task = submit_import(env, root)
    with Session(env.engine) as db:
        db.get(Task, task.id).payload = json.dumps({"import_id": batch.id})
        stored = db.get(ImageImport, batch.id)
        stored.fingerprint = scan_images(root, "yolo_detect", used_names=used_names).fingerprint
        if incremental:
            stored.class_mapping = json.dumps([{"source_id": 0, "new_label_name": "legacy-unused"}])
        db.commit()
    run_task(env, task.id)
    assert env.images.list_images(env.users["owner"], PROJECT)[2] == (4 if incremental else 3)
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(ImageDirectory.id))) == 3
        assert (
            db.scalar(select(func.count(ProjectLabel.id)).where(ProjectLabel.project_id == PROJECT))
            == 1
        )


def test_all_duplicate_create_api_returns_error_without_creating_a_task(env):
    imported(env)
    client = client_for(env)
    url = f"/api/v1/projects/{PROJECT}/image-imports"
    preview = client.post(url + "/preview", headers=ORIGIN, json={"root_path": "source"}).json()
    assert preview["new_images"] == 0 and preview["existing_images"] == 3
    response = client.post(
        url,
        headers=ORIGIN,
        json={
            "root_path": "source",
            "fingerprint": preview["fingerprint"],
            "confirm_warnings": True,
        },
    )
    assert response.status_code == 422, response.text
    assert "没有可新增" in response.json()["detail"]
    with Session(env.engine) as db:
        assert db.scalar(select(func.count(Task.id))) == 1
        assert db.scalar(select(func.count(ImageImport.id))) == 1


def test_incremental_unpublished_expired_lease_recovers_into_reused_directory(env):
    root = env.home / "source"
    picture(root / "old.png", 10)
    _, [old_image] = imported(env, root, "images")
    picture(root / "new.png", 11)
    batch, task = submit_import(env, root, "images")
    destination = env.workspace / "projects" / PROJECT / "images" / batch.id
    destination.mkdir()
    (destination / "uncommitted.txt").write_text("orphaned staging")
    with Session(env.engine) as db:
        stored = db.get(Task, task.id)
        stored.status, stored.lease_owner = "running", "dead-worker"
        stored.lease_expires_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(
            minutes=5
        )
        db.get(ImageImport, batch.id).status = "running"
        db.commit()
    result = json.loads(run_task(env, task.id))
    assert result["images"] == 1
    assert not (destination / "uncommitted.txt").exists()
    items, _, total, _ = env.images.list_images(env.users["owner"], PROJECT)
    assert total == 2 and {i.directory_id for i in items} == {old_image.directory_id}
    assert not list((env.workspace / "tmp").iterdir())


def test_list_summary_respects_label_and_enabled_filters(env):
    _, images = imported(env)
    positive = next(i for i in images if i.file_name == "train.png")
    env.images.change_enabled(
        env.users["owner"], PROJECT, [{"image_id": positive.id, "version": 1, "enabled": False}]
    )
    client = client_for(env)
    response = client.get(
        f"/api/v1/projects/{PROJECT}/images", params={"label_id": LABEL, "enabled": "false"}
    )
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert response.json()["summary"] == {"enabled_images": 0, "labeled_images": 1}


def test_import_task_api_omits_internal_recovery_ids_but_keeps_summary(env):
    root = yolo_fixture(env.home / "source")
    _, task = submit_import(env, root)
    result = json.loads(run_task(env, task.id))
    assert result["image_ids"]
    response = client_for(env).get(f"/api/v1/projects/{PROJECT}/tasks")
    assert response.status_code == 200
    returned = next(item for item in response.json()["items"] if item["id"] == task.id)
    assert "image_ids" not in returned["result"]
    assert returned["result"]["images"] == result["images"]
    with Session(env.engine) as db:
        assert json.loads(db.get(Task, task.id).result)["image_ids"] == result["image_ids"]


def test_filtered_image_batch_freezes_enabled_matching_images_and_checks_access(env, monkeypatch):
    root = env.home / "filtered-batch"
    for index, name in enumerate(
        [
            "alpha/keep-a.png",
            "alpha/keep-b.png",
            "alpha/keep-disabled.png",
            "alpha/other.png",
            "beta/keep-c.png",
        ]
    ):
        picture(root / name, index)
    _, images = imported(env, root, "images")
    directory = next(i.directory_id for i in images if i.file_name == "keep-a.png")
    disabled = next(i for i in images if i.file_name == "keep-disabled.png")
    with Session(env.engine) as db:
        db.get(ImageAsset, disabled.id).enabled = False
        db.commit()
    client = client_for(env)
    monkeypatch.setattr(
        client.app.state.auto_annotation_service, "_validate_model", lambda *_: None
    )
    url = f"/api/v1/projects/{PROJECT}/images/auto-annotations/filtered"
    config = {
        "model_id": "fake",
        "categories": ["object"],
        "confidence": 0.25,
        "iou": 0.7,
        "overwrite": False,
    }
    assert client.post(url, json=config).status_code == 403
    assert client_for(env, "viewer").post(url, headers=ORIGIN, json=config).status_code == 403
    response = client.post(
        url, params={"directory_id": directory, "search": "keep"}, headers=ORIGIN, json=config
    )
    assert response.status_code == 202, response.text
    with Session(env.engine) as db:
        payload = json.loads(db.get(Task, response.json()["id"]).payload)
    assert {item["id"] for item in payload["images"]} == {
        i.id
        for i in images
        if i.directory_id == directory and i.file_name in {"keep-a.png", "keep-b.png"}
    }
    assert payload["overwrite"] is False
    legacy = f"/api/v1/projects/{PROJECT}/images/auto-annotations"
    assert (
        client.post(legacy, headers=ORIGIN, json={**config, "image_ids": ["x"] * 201}).status_code
        == 422
    )
