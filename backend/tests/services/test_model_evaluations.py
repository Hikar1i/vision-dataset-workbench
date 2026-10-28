import json
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image
from sqlalchemy.orm import Session, sessionmaker

from vision_dataset_workbench.capabilities import GpuDevice
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.model_evaluation_task import execute_model_evaluation
from vision_dataset_workbench.models import (
    EvaluationDataset,
    InferenceModel,
    ModelArtifact,
    ModelEvaluation,
    ModelProject,
    Task,
    User,
)
from vision_dataset_workbench.services.gpu_leases import GpuLeaseService
from vision_dataset_workbench.services.model_evaluations import (
    ModelEvaluationConflict, ModelEvaluationError, ModelEvaluationService,
)
from vision_dataset_workbench.services.models import ModelService
from vision_dataset_workbench.services.projects import ProjectService


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
    settings = RuntimeSettings(home=tmp_path, workspace=workspace)
    projects = ProjectService(engine, settings, workspace)
    models = ModelService(engine, settings, workspace, projects)
    return engine, workspace, ModelEvaluationService(engine, workspace, models=models), owner


@pytest.mark.parametrize("validate_with_ultralytics", [False, True])
@pytest.mark.parametrize(
    "artifact_format,legacy", [("pt", False), ("onnx", False), ("engine", True)]
)
def test_evaluation_remaps_class_order_and_persists_metrics(
    tmp_path, monkeypatch, validate_with_ultralytics, artifact_format, legacy
):
    check_dataset = None
    if validate_with_ultralytics:
        config_dir = tmp_path / "yolo-config"
        config_dir.mkdir()
        monkeypatch.setenv("YOLO_CONFIG_DIR", str(config_dir))
        data_utils = pytest.importorskip("ultralytics.data.utils")
        # The dataset contract is real; font downloads are unrelated and must stay offline.
        monkeypatch.setattr(data_utils, "check_font", lambda *_args: None)
        check_dataset = data_utils.check_det_dataset
    engine, workspace, service, owner = setup(tmp_path)
    source = workspace / "model-projects/project/evaluation-datasets/dataset"
    Image.new("RGB", (8, 8), "black").save(source / "images/negative.png")
    Image.new("RGB", (8, 8), "red").save(source / "images/car.png")
    (source / "labels/negative.txt").write_text("")
    (source / "labels/car.txt").write_text("1 0.5 0.5 0.3 0.3\n")
    original_files = {path: path.read_bytes() for path in source.rglob("*") if path.is_file()}
    with Session(engine) as database:
        dataset = database.get(EvaluationDataset, "dataset")
        dataset.image_count = 3
        dataset.label_count = 2
        dataset.negative_count = 1
        database.commit()
    image_size = 640 if artifact_format == "pt" else 64
    if artifact_format != "pt":
        with Session(engine) as database:
            database.add(
                ModelArtifact(
                    model_id="model",
                    format=artifact_format,
                    status="ready",
                    source_model_sha256="a" * 64,
                    sha256="c" * 64,
                    storage_path=f"models/model/model.{artifact_format}",
                    export_config=json.dumps({"imgsz": image_size}),
                    created_by_id="owner",
                )
            )
            database.commit()
    evaluation, task = service.create_evaluation(
        owner, "project", "model", "dataset", artifact_format
    )
    assert json.loads(evaluation.config)["imgsz"] == image_size
    with Session(engine) as database:
        if legacy:
            stored_evaluation = database.get(ModelEvaluation, evaluation.id)
            config = json.loads(stored_evaluation.config)
            config.pop("imgsz")
            stored_evaluation.config = json.dumps(config)
        stored = database.get(Task, task.id)
        stored.status = "running"
        database.commit()

    calls = []

    class FakeYolo:
        names = {0: "car", 1: "plane"}

        def __init__(self, _path):
            self.overrides = {}

        def val(self, **arguments):
            calls.append(arguments)
            assert self.overrides["device"] == arguments["device"] == 1
            assert arguments["imgsz"] == image_size
            config = json.loads(Path(arguments["data"]).read_text())
            if check_dataset:
                checked = check_dataset(arguments["data"], autodownload=False, split="val")
                assert (
                    checked["train"]
                    == checked["val"]
                    == str(Path(arguments["data"]).parent / "images")
                )
                assert checked["names"] == {0: "car", 1: "plane"}
            assert config["train"] == config["val"] == "images"
            assert arguments["split"] == "val"
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
        executor,
        "importlib",
        SimpleNamespace(import_module=lambda _name: SimpleNamespace(YOLO=FakeYolo)),
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
        GpuLeaseService(engine, devices=(GpuDevice(1, "GPU", 1024, "GPU-a", "8.6"),)),
    )
    assert len(calls) == 1
    assert (temp / "prepared" / "labels" / "sample.txt").read_text().startswith("1 ")
    assert (temp / "prepared" / "labels" / "car.txt").read_text().startswith("0 ")
    assert (temp / "prepared" / "labels" / "negative.txt").read_text() == ""
    assert len(list((temp / "prepared" / "images").iterdir())) == 3
    assert all(path.read_bytes() == content for path, content in original_files.items())
    with Session(engine) as database:
        stored = database.get(ModelEvaluation, evaluation.id)
        assert stored.status == "succeeded"
        assert json.loads(stored.class_mapping) == {"0": 1, "1": 0}
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
        "format": artifact_format,
        "dataset_name": "Eval",
        "dataset_hash": "b" * 64,
    }
    engine.dispose()


def test_delete_evaluation_requires_access_and_finished_task(tmp_path):
    engine, workspace, service, owner = setup(tmp_path)
    evaluation, task = service.create_evaluation(owner, "project", "model", "dataset", "pt")
    with pytest.raises(ModelEvaluationConflict):
        service.delete_evaluation(owner, evaluation.id)
    with Session(engine) as database:
        database.get(ModelEvaluation, evaluation.id).status = "failed"
        database.get(Task, task.id).status = "failed"
        outsider = User(id="outsider", username="outsider", username_normalized="outsider", password_hash="x")
        database.add(outsider)
        database.commit()
        database.refresh(outsider)
        database.expunge(outsider)
    with pytest.raises(ModelEvaluationError):
        service.delete_evaluation(outsider, evaluation.id)
    directory = workspace / "model-projects/project/evaluations" / evaluation.id
    directory.mkdir(parents=True)
    (directory / "plot.png").write_bytes(b"plot")
    service.delete_evaluation(owner, evaluation.id)
    assert not directory.exists()
    assert service.list_evaluations(owner, "project") == []
    with Session(engine) as database:
        assert database.get(Task, task.id) is not None
        assert database.get(InferenceModel, "model") is not None
        assert database.get(EvaluationDataset, "dataset") is not None
