from fastapi.testclient import TestClient
from io import BytesIO
import json
from urllib.parse import quote
import zipfile
import pytest
from PIL import Image
from sqlalchemy.orm import Session

from vision_dataset_workbench.capabilities import (
    CapabilityStatus,
    FeatureCapabilities,
    GpuDevice,
    GpuStatus,
    SystemCapabilities,
)
from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import (
    EvaluationDataset,
    InferenceModel,
    ModelArtifact,
    ModelProjectMembership,
    Task,
    User,
)
from vision_dataset_workbench.inference import Detection
from vision_dataset_workbench.security.passwords import hash_password

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


def capabilities():
    yes = CapabilityStatus(True)
    return SystemCapabilities(
        gpu=GpuStatus(True, None, (GpuDevice(0, "A4000", 16000, "GPU-a", "8.6"),)),
        pytorch_cuda=yes,
        features=FeatureCapabilities(yes, yes, yes, yes, yes, yes),
    )


def client_for(app, username):
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/login",
            headers=ORIGIN,
            json={"username": username, "password": PASSWORD},
        ).status_code
        == 200
    )
    return client


def setup_app(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    home.mkdir()
    create_workspace_database(workspace / "db" / "workbench.sqlite3")
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    with Session(engine) as database:
        database.add_all(
            [
                User(
                    id="admin-id",
                    username="admin",
                    username_normalized="admin",
                    password_hash=hash_password(PASSWORD),
                    is_system_admin=True,
                ),
                User(
                    id="viewer-id",
                    username="viewer",
                    username_normalized="viewer",
                    password_hash=hash_password(PASSWORD),
                ),
            ]
        )
        database.commit()
    engine.dispose()
    app = create_app(RuntimeSettings(home=home, workspace=workspace), capabilities=capabilities())
    admin, viewer = client_for(app, "admin"), client_for(app, "viewer")
    project = admin.post(
        "/api/v1/model-projects",
        headers=ORIGIN,
        json={"name": "Models", "description": ""},
    ).json()
    with app.state.model_service._session_factory() as database:
        database.add(
            ModelProjectMembership(
                model_project_id=project["id"], user_id="viewer-id", role="viewer"
            )
        )
        database.commit()
    source = workspace / "models" / "model-id" / "best.pt"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"weights")
    with app.state.model_service._session_factory() as database:
        database.add(
            InferenceModel(
                id="model-id",
                model_project_id=project["id"],
                name="Detector",
                model_code="detector",
                kind="yolo",
                status="ready",
                storage_path=source.relative_to(workspace).as_posix(),
                file_size=source.stat().st_size,
                sha256="a" * 64,
                source_name="best.pt",
                created_by_id="admin-id",
            )
        )
        database.commit()
    return app, admin, viewer, workspace


def test_model_artifact_api_permissions_download_and_stale_state(tmp_path):
    app, admin, viewer, workspace = setup_app(tmp_path)
    url = "/api/v1/models/model-id/artifacts"

    assert admin.post(url, json={"format": "onnx"}).status_code == 403
    assert viewer.post(url, headers=ORIGIN, json={"format": "onnx"}).status_code == 403
    created = admin.post(
        url,
        headers=ORIGIN,
        json={"format": "onnx", "image_size": 640, "dynamic": True},
    )
    assert created.status_code == 202
    artifact_id = created.json()["artifact"]["id"]
    assert created.json()["task"]["type"] == "convert_model"
    assert viewer.get(url).json()[0]["status"] == "queued"

    target = workspace / "models" / "model-id" / "artifacts" / "model.onnx"
    target.parent.mkdir()
    target.write_bytes(b"onnx")
    with app.state.model_artifact_service._session_factory() as database:
        artifact = database.get(ModelArtifact, artifact_id)
        artifact.status = "ready"
        artifact.storage_path = target.relative_to(workspace).as_posix()
        artifact.file_size = target.stat().st_size
        artifact.sha256 = "b" * 64
        task = database.get(Task, artifact.task_id)
        task.status = "succeeded"
        database.commit()

    downloaded = viewer.get(f"/api/v1/model-artifacts/{artifact_id}/download")
    assert downloaded.status_code == 200 and downloaded.content == b"onnx"
    assert 'filename="detector-onnx-' in downloaded.headers["content-disposition"]
    assert (
        viewer.delete(f"/api/v1/model-artifacts/{artifact_id}", headers=ORIGIN).status_code == 403
    )

    with app.state.model_artifact_service._session_factory() as database:
        model = database.get(InferenceModel, "model-id")
        model.sha256 = "c" * 64
        database.commit()
    assert admin.get(url).json()[0]["status"] == "stale"
    assert admin.get(f"/api/v1/model-artifacts/{artifact_id}/download").status_code == 409
    assert admin.delete(f"/api/v1/model-artifacts/{artifact_id}", headers=ORIGIN).status_code == 204


@pytest.mark.parametrize(
    "filename_headers",
    [
        {"X-Filename": "sample.png"},
        {"X-Filename": "%2F.png"},
        {"X-Filename-Encoded": quote("图像 100% + #😀.png")},
        {"X-Filename-Encoded": quote("图" * 200 + ".png")},
    ],
)
def test_image_inference_api_restores_downloads_and_saves_session(tmp_path, filename_headers):
    app, admin, _viewer, _workspace = setup_app(tmp_path)

    class Runner:
        def predict(self, *_args, **_kwargs):
            return [Detection("car", 1, 1, 10, 10, 0.9)]

    app.state.model_inference_service.runner = Runner()
    image = BytesIO()
    Image.new("RGB", (24, 24), "white").save(image, format="PNG")
    created = admin.post(
        "/api/v1/models/model-id/inference?input_type=image&format=pt",
        headers={**ORIGIN, **filename_headers},
        content=image.getvalue(),
    )
    assert created.status_code == 202, created.text
    run = created.json()
    assert run["status"] == "succeeded" and run["statistics"]["detections"] == 1
    assert admin.get("/api/v1/models/model-id/inference/current").json()["id"] == run["id"]
    assert admin.get(f"/api/v1/model-inference/{run['id']}/files/source").status_code == 200
    assert admin.get(f"/api/v1/model-inference/{run['id']}/files/result").status_code == 200
    saved = admin.post(f"/api/v1/model-inference/{run['id']}/save", headers=ORIGIN)
    assert saved.status_code == 200 and saved.json()["saved_at"]
    assert admin.get("/api/v1/models/model-id/inference/current").json() is None


@pytest.mark.parametrize(
    "filename_headers",
    [{"X-Filename": "set.zip"}, {"X-Filename-Encoded": quote("安全帽测试集 100%.ZIP")}],
)
def test_evaluation_dataset_and_evaluation_api_permissions(tmp_path, filename_headers):
    app, admin, viewer, workspace = setup_app(tmp_path)
    image = BytesIO()
    Image.new("RGB", (8, 8), "white").save(image, format="PNG")
    archive = BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("classes.txt", "car\n")
        bundle.writestr("images/sample.png", image.getvalue())
        bundle.writestr("labels/sample.txt", "0 0.5 0.5 0.2 0.2\n")
    project_id = admin.get("/api/v1/model-projects").json()[0]["id"]
    url = f"/api/v1/model-projects/{project_id}/evaluation-datasets?name=Safety"
    headers = {**ORIGIN, **filename_headers}
    assert viewer.post(url, headers=headers, content=archive.getvalue()).status_code == 403
    created = admin.post(url, headers=headers, content=archive.getvalue())
    assert created.status_code == 202, created.text
    dataset_id = created.json()["dataset"]["id"]
    dataset_path = workspace / "model-projects" / project_id / "evaluation-datasets" / dataset_id
    (dataset_path / "images").mkdir(parents=True)
    with app.state.model_evaluation_service._session_factory() as database:
        dataset = database.get(EvaluationDataset, dataset_id)
        dataset.status = "ready"
        dataset.storage_path = dataset_path.relative_to(workspace).as_posix()
        dataset.content_sha256 = "d" * 64
        dataset.classes = json.dumps(["car"])
        dataset.image_count = dataset.label_count = 1
        database.commit()
    evaluation = admin.post(
        f"/api/v1/model-projects/{project_id}/evaluations",
        headers=ORIGIN,
        json={"model_id": "model-id", "dataset_id": dataset_id, "format": "pt"},
    )
    assert evaluation.status_code == 202, evaluation.text
    assert evaluation.json()["evaluation"]["config"]["conf"] == 0.001
    assert viewer.get(f"/api/v1/model-projects/{project_id}/evaluations").status_code == 200


def test_chinese_video_upload_is_queued_without_running_inference(tmp_path):
    app, admin, _viewer, workspace = setup_app(tmp_path)
    created = admin.post(
        "/api/v1/models/model-id/inference?input_type=video&format=pt",
        headers={**ORIGIN, "X-Filename-Encoded": quote(r"C:\fakepath\中文视频 100%.mp4")},
        content=b"isolated-video-placeholder",
    )
    assert created.status_code == 202, created.text
    run = created.json()
    assert run["status"] == "queued"
    with app.state.model_inference_service._session_factory() as database:
        task = database.get(Task, run["task_id"])
        assert task.type == "infer_video" and task.status == "queued"
    downloaded = admin.get(f"/api/v1/model-inference/{run['id']}/files/source")
    assert downloaded.status_code == 200
    assert downloaded.content == b"isolated-video-placeholder"
    assert list(workspace.rglob("source.mp4"))


def test_upload_endpoints_reject_invalid_filename_headers_before_writing_files(tmp_path):
    app, admin, _viewer, workspace = setup_app(tmp_path)
    project_id = admin.get("/api/v1/model-projects").json()[0]["id"]
    urls = [
        "/api/v1/models/model-id/inference?input_type=image",
        f"/api/v1/model-projects/{project_id}/evaluation-datasets?name=Invalid",
    ]
    for url in urls:
        for encoded in ["%FF.png", "bad%", "bad%0D%0Aname.zip", "a" * 513, "%F0%9F%98%80" * 513]:
            response = admin.post(
                url,
                headers={**ORIGIN, "X-Filename": "safe.zip", "X-Filename-Encoded": encoded},
                content=b"must-not-be-written",
            )
            assert response.status_code == 422, response.text
    assert not (workspace / "tmp/inference-uploads").exists()
    assert not (workspace / "tmp/evaluation-api").exists()
    with app.state.model_evaluation_service._session_factory() as database:
        assert database.query(Task).count() == 0
        assert database.query(EvaluationDataset).count() == 0


@pytest.mark.parametrize("model_format", ["pt", "onnx", "engine"])
def test_cpu_rejects_new_local_runs_before_upload_and_keeps_read_access(tmp_path, model_format):
    app, admin, viewer, workspace = setup_app(tmp_path)
    no = CapabilityStatus(False, "CPU 版本不支持本地模型运行")
    app.state.capabilities = SystemCapabilities(
        gpu=GpuStatus(False, no.reason, ()),
        pytorch_cuda=no,
        features=FeatureCapabilities(CapabilityStatus(True), no, no, no, no, no),
    )
    project_id = admin.get("/api/v1/models/model-id").json()["model_project_id"]
    inference_url = f"/api/v1/models/model-id/inference?input_type=video&format={model_format}"
    evaluation_url = f"/api/v1/model-projects/{project_id}/evaluations"
    payload = {"model_id": "model-id", "dataset_id": "missing", "format": model_format}
    for client in (admin, viewer):
        expected = 409 if client is admin else 403
        assert (
            client.post(inference_url, headers=ORIGIN, content=b"not uploaded").status_code
            == expected
        )
        assert client.post(evaluation_url, headers=ORIGIN, json=payload).status_code == expected
    assert not (workspace / "tmp/inference-uploads").exists()
    assert admin.get("/api/v1/models/model-id/inference/current").status_code == 200
    assert admin.get(f"/api/v1/model-projects/{project_id}/evaluation-datasets").status_code == 200
    with app.state.model_service._session_factory() as db:
        assert db.query(Task).count() == 0
