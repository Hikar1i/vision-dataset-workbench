import io
import json
import zipfile
from datetime import datetime

import pytest
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.evaluation_dataset_task import (
    execute_evaluation_dataset_import,
    validate_evaluation_zip,
)
from vision_dataset_workbench.models import EvaluationDataset, ModelProject, Task, User
from vision_dataset_workbench.services.model_evaluations import ModelEvaluationService


def png_bytes():
    output = io.BytesIO()
    Image.new("RGB", (8, 8), "white").save(output, format="PNG")
    return output.getvalue()


def make_zip(path, *, wrapper="", label="0 0.5 0.5 0.25 0.25\n", extra=None):
    prefix = f"{wrapper}/" if wrapper else ""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as bundle:
        bundle.writestr(f"{prefix}classes.txt", "car\nplane\n")
        bundle.writestr(f"{prefix}images/sample.png", png_bytes())
        bundle.writestr(f"{prefix}labels/sample.txt", label)
        if extra:
            bundle.writestr(extra[0], extra[1])


def setup(tmp_path):
    workspace = tmp_path / "workspace"
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    with Session(engine) as database:
        database.add(
            User(id="owner", username="owner", username_normalized="owner", password_hash="x")
        )
        database.flush()
        database.add(
            ModelProject(
                id="project",
                name="Models",
                name_normalized="models",
                series_type="archive",
                created_by_id="owner",
            )
        )
        database.commit()
        owner = database.get(User, "owner")
        database.expunge(owner)
    return engine, workspace, ModelEvaluationService(engine, workspace), owner


def test_zip_validation_accepts_simple_and_wrapped_layout_and_hashes_content(tmp_path):
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"
    make_zip(first)
    make_zip(second, wrapper="evaluation")
    one = validate_evaluation_zip(first, tmp_path / "one")
    two = validate_evaluation_zip(second, tmp_path / "two")
    assert one == two
    assert one["classes"] == ["car", "plane"]
    assert one["image_count"] == 1 and one["negative_count"] == 0


@pytest.mark.parametrize(
    ("extra", "label", "message"),
    [
        (("../escape.txt", "bad"), "0 0.5 0.5 0.2 0.2", "不安全路径"),
        (("notes/readme.txt", "bad"), "0 0.5 0.5 0.2 0.2", "仅允许"),
        (None, "4 0.5 0.5 0.2 0.2", "越界"),
        (None, "0 0.5 0.5 0.2", "五列"),
    ],
)
def test_zip_validation_rejects_unrelated_or_unsafe_content(tmp_path, extra, label, message):
    archive = tmp_path / "invalid.zip"
    make_zip(archive, label=label, extra=extra)
    with pytest.raises(ValueError, match=message):
        validate_evaluation_zip(archive, tmp_path / "output")


def test_dataset_import_task_publishes_immutable_snapshot(tmp_path):
    engine, workspace, service, owner = setup(tmp_path)
    archive = tmp_path / "dataset.zip"
    make_zip(archive, label="")
    dataset, task = service.create_dataset(owner, "project", "Safety set", archive)
    with Session(engine) as database:
        stored = database.get(Task, task.id)
        stored.status = "running"
        database.commit()
    temp = workspace / "tmp" / task.id
    temp.mkdir(parents=True)
    execute_evaluation_dataset_import(
        sessionmaker(engine, expire_on_commit=False),
        workspace,
        task.id,
        temp,
        datetime.now,
        lambda _task_id, _progress: None,
    )
    with Session(engine) as database:
        stored = database.get(EvaluationDataset, dataset.id)
        assert stored.status == "ready"
        assert stored.negative_count == 1
        assert json.loads(stored.classes) == ["car", "plane"]
        assert (workspace / stored.storage_path / "images" / "sample.png").is_file()
    engine.dispose()
