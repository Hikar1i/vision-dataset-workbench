from types import SimpleNamespace

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from vision_dataset_workbench.capabilities import detect_capabilities
from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.main import create_app
from vision_dataset_workbench.models import User
from vision_dataset_workbench.security.passwords import hash_password

ORIGIN = {"Origin": "http://testserver"}
PASSWORD = "correct horse battery staple"


def module_loader(*, torch=True, onnx=True):
    modules = {}
    if torch:
        modules["torch"] = SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: True)
        )
    if onnx:
        modules["onnxruntime"] = SimpleNamespace(
            get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
    def load(name):
        if name not in modules:
            raise ModuleNotFoundError(name)
        return modules[name]

    return load


def module_finder(ultralytics=True):
    return lambda name: object() if name == "ultralytics" and ultralytics else None


def test_detects_multiple_gpus_and_ready_model_runtimes():
    capabilities = detect_capabilities(
        run_command=lambda _: "0, NVIDIA RTX A4000, 16376\n1, Quadro RTX 4000, 8192\n",
        load_module=module_loader(),
        find_module=module_finder(),
    )

    assert capabilities.gpu.available is True
    assert [(item.index, item.name, item.memory_total_mb) for item in capabilities.gpu.devices] == [
        (0, "NVIDIA RTX A4000", 16376),
        (1, "Quadro RTX 4000", 8192),
    ]
    assert capabilities.pytorch_cuda.available is True
    assert capabilities.onnx_cuda.available is True
    assert capabilities.features.manual_annotation.available is True
    assert capabilities.features.yolo_auto_annotation.available is True
    assert capabilities.features.grounding_dino_auto_annotation.available is True
    assert capabilities.features.model_training.available is True


def test_probe_failures_disable_gpu_features_without_raising():
    def missing_command(_):
        raise FileNotFoundError("nvidia-smi")

    capabilities = detect_capabilities(
        run_command=missing_command,
        load_module=module_loader(torch=False, onnx=False),
        find_module=module_finder(False),
    )

    assert capabilities.gpu.available is False
    assert capabilities.gpu.devices == ()
    assert capabilities.pytorch_cuda.available is False
    assert capabilities.onnx_cuda.available is False
    assert capabilities.features.manual_annotation.available is True
    assert capabilities.features.yolo_auto_annotation.available is False
    assert capabilities.features.grounding_dino_auto_annotation.available is False
    assert capabilities.features.model_training.available is False


def test_yolo_requires_ultralytics_in_addition_to_pytorch_cuda():
    capabilities = detect_capabilities(
        run_command=lambda _: "0, NVIDIA RTX A4000, 16376\n",
        load_module=module_loader(),
        find_module=module_finder(False),
    )

    assert capabilities.pytorch_cuda.available is True
    assert capabilities.features.yolo_auto_annotation.available is False
    assert capabilities.features.yolo_auto_annotation.reason == "未安装 Ultralytics 运行依赖"


def test_capabilities_api_requires_authentication_and_returns_cached_result(tmp_path):
    home = tmp_path / "home"
    workspace = home / ".vision-dataset-workbench"
    (workspace / "projects").mkdir(parents=True)
    database_path = workspace / "db" / "workbench.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    with Session(engine) as session:
        session.add(
            User(
                username="admin",
                username_normalized="admin",
                password_hash=hash_password(PASSWORD),
                status="active",
                is_system_admin=True,
            )
        )
        session.commit()
    engine.dispose()
    detected = detect_capabilities(
        run_command=lambda _: "0, NVIDIA RTX A4000, 16376\n",
        load_module=module_loader(),
        find_module=module_finder(),
    )
    app = create_app(
        RuntimeSettings(home=home, workspace=workspace), capabilities=detected
    )
    client = TestClient(app)

    assert client.get("/api/v1/capabilities").status_code == 401
    assert client.post(
        "/api/v1/auth/login",
        headers=ORIGIN,
        json={"username": "admin", "password": PASSWORD},
    ).status_code == 200
    response = client.get("/api/v1/capabilities")

    assert response.status_code == 200
    assert response.json()["gpu"]["devices"][0]["name"] == "NVIDIA RTX A4000"
    assert response.json()["features"]["yolo_auto_annotation"]["available"] is True
