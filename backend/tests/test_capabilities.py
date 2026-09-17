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


def module_loader(*, torch=True, onnxruntime=True, tensorrt=True):
    modules = {}
    if torch:
        modules["torch"] = SimpleNamespace(
            cuda=SimpleNamespace(is_available=lambda: True)
        )
    if onnxruntime:
        modules["onnxruntime"] = SimpleNamespace(
            get_available_providers=lambda: ["CUDAExecutionProvider", "CPUExecutionProvider"]
        )
    if tensorrt:
        class Logger:
            ERROR = 1

            def __init__(self, _level):
                pass

        modules["tensorrt"] = SimpleNamespace(
            Logger=Logger,
            Builder=lambda _logger: object(),
        )
    def load(name):
        if name not in modules:
            raise ModuleNotFoundError(name)
        return modules[name]

    return load


def module_finder(*, ultralytics=True, onnx=True, onnxslim=True):
    available = {
        "ultralytics": ultralytics,
        "onnx": onnx,
        "onnxslim": onnxslim,
    }
    return lambda name: object() if available.get(name, False) else None


def test_detects_multiple_gpus_and_ready_model_runtimes():
    capabilities = detect_capabilities(
        run_command=lambda _: (
            "0, GPU-a, NVIDIA RTX A4000, 8.6, 16376\n"
            "1, GPU-b, Quadro RTX 4000, 7.5, 8192\n"
        ),
        load_module=module_loader(),
        find_module=module_finder(),
    )

    assert capabilities.gpu.available is True
    assert [
        (item.index, item.uuid, item.name, item.compute_capability, item.memory_total_mb)
        for item in capabilities.gpu.devices
    ] == [
        (0, "GPU-a", "NVIDIA RTX A4000", "8.6", 16376),
        (1, "GPU-b", "Quadro RTX 4000", "7.5", 8192),
    ]
    assert capabilities.pytorch_cuda.available is True
    assert capabilities.features.manual_annotation.available is True
    assert capabilities.features.yolo_auto_annotation.available is True
    assert capabilities.features.model_training.available is True
    assert capabilities.features.onnx_export.available is True
    assert capabilities.features.onnx_inference.available is True
    assert capabilities.features.tensorrt.available is True


def test_probe_failures_disable_gpu_features_without_raising():
    def missing_command(_):
        raise FileNotFoundError("nvidia-smi")

    capabilities = detect_capabilities(
        run_command=missing_command,
        load_module=module_loader(torch=False),
        find_module=module_finder(ultralytics=False, onnx=False, onnxslim=False),
    )

    assert capabilities.gpu.available is False
    assert capabilities.gpu.devices == ()
    assert capabilities.pytorch_cuda.available is False
    assert capabilities.features.manual_annotation.available is True
    assert capabilities.features.yolo_auto_annotation.available is False
    assert capabilities.features.model_training.available is False
    assert capabilities.features.onnx_export.available is False
    assert capabilities.features.onnx_inference.available is False
    assert capabilities.features.tensorrt.available is False


def test_yolo_requires_ultralytics_in_addition_to_pytorch_cuda():
    capabilities = detect_capabilities(
        run_command=lambda _: "0, GPU-a, NVIDIA RTX A4000, 8.6, 16376\n",
        load_module=module_loader(),
        find_module=module_finder(ultralytics=False),
    )

    assert capabilities.pytorch_cuda.available is True
    assert capabilities.features.yolo_auto_annotation.available is False
    assert capabilities.features.yolo_auto_annotation.reason == "未安装 Ultralytics 运行依赖"


def test_model_runtime_capabilities_report_missing_components():
    capabilities = detect_capabilities(
        run_command=lambda _: "0, GPU-a, NVIDIA RTX A4000, 8.6, 16376\n",
        load_module=module_loader(onnxruntime=False, tensorrt=False),
        find_module=module_finder(onnx=False, onnxslim=False),
    )

    assert capabilities.features.onnx_export.available is False
    assert "ONNX" in (capabilities.features.onnx_export.reason or "")
    assert capabilities.features.onnx_inference.available is False
    assert "ONNX Runtime" in (capabilities.features.onnx_inference.reason or "")
    assert capabilities.features.tensorrt.available is False
    assert "TensorRT" in (capabilities.features.tensorrt.reason or "")


def test_onnx_inference_requires_cuda_execution_provider():
    loader = module_loader()

    def load(name):
        if name == "onnxruntime":
            return SimpleNamespace(get_available_providers=lambda: ["CPUExecutionProvider"])
        return loader(name)

    capabilities = detect_capabilities(
        run_command=lambda _: "0, GPU-a, NVIDIA RTX A4000, 8.6, 16376\n",
        load_module=load,
        find_module=module_finder(),
    )

    assert capabilities.features.onnx_inference.available is False
    assert capabilities.features.onnx_inference.reason == "ONNX Runtime CUDA Provider 不可用"


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
        run_command=lambda _: "0, GPU-a, NVIDIA RTX A4000, 8.6, 16376\n",
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
