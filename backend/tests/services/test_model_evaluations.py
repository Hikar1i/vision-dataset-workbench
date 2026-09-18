import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from vision_dataset_workbench.capabilities import GpuDevice
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.model_evaluation_task import execute_model_evaluation
from vision_dataset_workbench.models import (
    EvaluationDataset,
    InferenceModel,
    ModelEvaluation,
    ModelProject,
    Task,
    User,
)
from vision_dataset_workbench.services.gpu_leases import GpuLeaseService
from vision_dataset_workbench.services.model_evaluations import ModelEvaluationService


def setup(tmp_path):
    workspace = tmp_path / "workspace"
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    model_path = workspace / "models" / "model" / "best.pt"
    model_path.parent.mkdir(parents=True)
    model_path.write_bytes(b"weights")
    dataset_path = workspace / "model-projects" / "project" / "evaluation-datasets" / "dataset"
    (dataset_path / "images").mkdir(parents=True)
    (dataset_path / "labels").mkdir()
    Image.new("RGB", (8, 8), "white").save(dataset_path / "images" / "sample.png")
    (dataset_path / "labels" / "sample.txt").write_text("0 0.5 0.5 0.2 0.2\n")
    (dataset_path / "classes.txt").write_text("plane\ncar\n")
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
        database.flush()
        database.add(
            InferenceModel(
                id="model",
                model_project_id="project",
                model_code="model",
                name="Detector",
                kind="yolo",
                status="ready",
                storage_path="models/model/best.pt",
                sha256="a" * 64,
                source_name="best.pt",
                created_by_id="owner",
            )
        )
        database.add(
            EvaluationDataset(
                id="dataset",
                model_project_id="project",
                name="Eval",
                content_sha256="b" * 64,
                storage_path=dataset_path.relative_to(workspace).as_posix(),
                classes=json.dumps(["plane", "car"]),
                image_count=1,
                label_count=1,
                total_bytes=10,
                status="ready",
                created_by_id="owner",
            )
        )
        database.commit()
        owner = database.get(User, "owner")
        database.expunge(owner)
    return engine, workspace, ModelEvaluationService(engine, workspace), owner


def test_evaluation_remaps_class_order_and_persists_metrics(tmp_path, monkeypatch):
    engine, workspace, service, owner = setup(tmp_path)
    evaluation, task = service.create_evaluation(owner, "project", "model", "dataset", "pt")
    with Session(engine) as database:
        stored = database.get(Task, task.id)
        stored.status = "running"
        database.commit()

    class FakeYolo:
        names = {0: "car", 1: "plane"}

        def __init__(self, _path):
            pass

        def val(self, **arguments):
            output = Path(arguments["project"]) / arguments["name"]
            output.mkdir()
            (output / "confusion_matrix.png").write_bytes(b"png")
            (output / "BoxPR_curve.png").write_bytes(b"png")
            box = SimpleNamespace(mp=0.8, mr=0.7, map50=0.75, map=0.6, maps=[0.55, 0.65])
            return SimpleNamespace(
                box=box, speed={"preprocess": 1, "inference": 2, "postprocess": 3}
            )

    import vision_dataset_workbench.model_evaluation_task as executor

    monkeypatch.setattr(
        executor.importlib, "import_module", lambda _name: SimpleNamespace(YOLO=FakeYolo)
    )
    temp = workspace / "tmp" / task.id
    temp.mkdir(parents=True)
    execute_model_evaluation(
        sessionmaker(engine, expire_on_commit=False),
        workspace,
        task.id,
        temp,
        datetime.now,
        lambda _id, _progress: None,
        lambda _id: False,
        GpuLeaseService(engine, devices=(GpuDevice(0, "GPU", 1024, "GPU-a", "8.6"),)),
    )
    assert (temp / "prepared" / "labels" / "sample.txt").read_text().startswith("1 ")
    with Session(engine) as database:
        stored = database.get(ModelEvaluation, evaluation.id)
        assert stored.status == "succeeded"
        assert json.loads(stored.metrics)["map50_95"] == 0.6
        assert stored.confusion_matrix_path and stored.pr_curve_path
        database.add(
            ModelEvaluation(
                id="newer-lower-score",
                model_project_id="project",
                model_id="model",
                model_name="Detector",
                source_model_sha256="a" * 64,
                format="pt",
                evaluation_dataset_id="dataset",
                dataset_name="Newer Eval",
                dataset_sha256="c" * 64,
                metrics=json.dumps({"map50_95": 0.5}),
                status="succeeded",
                created_by_id="owner",
                finished_at=datetime(2030, 1, 1),
            )
        )
        database.commit()
    assert service.peak_model_metric("model") == {
        "id": evaluation.id,
        "map50_95": 0.6,
        "format": "pt",
        "dataset_name": "Eval",
        "dataset_hash": "b" * 64,
    }
    engine.dispose()
