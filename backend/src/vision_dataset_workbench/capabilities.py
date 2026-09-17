import csv
import importlib
import importlib.util
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from io import StringIO
from types import ModuleType


@dataclass(frozen=True)
class CapabilityStatus:
    available: bool
    reason: str | None = None


@dataclass(frozen=True)
class GpuDevice:
    index: int
    name: str
    memory_total_mb: int
    uuid: str = ""
    compute_capability: str = ""


@dataclass(frozen=True)
class GpuStatus:
    available: bool
    reason: str | None
    devices: tuple[GpuDevice, ...]


@dataclass(frozen=True)
class FeatureCapabilities:
    manual_annotation: CapabilityStatus
    yolo_auto_annotation: CapabilityStatus
    model_training: CapabilityStatus
    onnx_export: CapabilityStatus = CapabilityStatus(False, "ONNX 导出能力未检测")
    onnx_inference: CapabilityStatus = CapabilityStatus(False, "ONNX 推理能力未检测")
    tensorrt: CapabilityStatus = CapabilityStatus(False, "TensorRT 能力未检测")


@dataclass(frozen=True)
class SystemCapabilities:
    gpu: GpuStatus
    pytorch_cuda: CapabilityStatus
    features: FeatureCapabilities


def _run_nvidia_smi(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        capture_output=True,
        check=True,
        text=True,
        timeout=3,
    )
    return completed.stdout


def _detect_gpu(run_command: Callable[[list[str]], str]) -> GpuStatus:
    try:
        output = run_command(
            [
                "nvidia-smi",
                "--query-gpu=index,uuid,name,compute_cap,memory.total",
                "--format=csv,noheader,nounits",
            ]
        )
        devices = tuple(
            GpuDevice(
                index=int(row[0].strip()),
                uuid=row[1].strip(),
                name=row[2].strip(),
                compute_capability=row[3].strip(),
                memory_total_mb=int(float(row[4].strip())),
            )
            for row in csv.reader(StringIO(output))
            if len(row) == 5
        )
    except FileNotFoundError:
        return GpuStatus(False, "未检测到 nvidia-smi，GPU 功能未启用", ())
    except subprocess.TimeoutExpired:
        return GpuStatus(False, "GPU 检测超时", ())
    except Exception:
        return GpuStatus(False, "未检测到可用 NVIDIA GPU", ())
    if not devices:
        return GpuStatus(False, "未检测到可用 NVIDIA GPU", ())
    return GpuStatus(True, None, devices)


def _detect_pytorch(load_module: Callable[[str], ModuleType]) -> CapabilityStatus:
    try:
        torch = load_module("torch")
        if torch.cuda.is_available():
            return CapabilityStatus(True)
    except ModuleNotFoundError:
        return CapabilityStatus(False, "未安装 PyTorch GPU 运行依赖")
    except Exception:
        return CapabilityStatus(False, "PyTorch CUDA 初始化失败")
    return CapabilityStatus(False, "PyTorch CUDA 运行时不可用")


def _detect_ultralytics(find_module: Callable[[str], object | None]) -> CapabilityStatus:
    try:
        if find_module("ultralytics") is not None:
            return CapabilityStatus(True)
    except Exception:
        return CapabilityStatus(False, "Ultralytics 依赖检测失败")
    return CapabilityStatus(False, "未安装 Ultralytics 运行依赖")


def _detect_onnx_export(
    find_module: Callable[[str], object | None],
) -> CapabilityStatus:
    try:
        missing = [name for name in ("ultralytics", "onnx", "onnxslim") if find_module(name) is None]
    except Exception:
        return CapabilityStatus(False, "ONNX 导出依赖检测失败")
    if missing:
        return CapabilityStatus(False, f"未安装 ONNX 导出依赖：{', '.join(missing)}")
    return CapabilityStatus(True)


def _detect_onnx_inference(
    load_module: Callable[[str], ModuleType],
) -> CapabilityStatus:
    try:
        runtime = load_module("onnxruntime")
        if "CUDAExecutionProvider" not in runtime.get_available_providers():
            return CapabilityStatus(False, "ONNX Runtime CUDA Provider 不可用")
    except ModuleNotFoundError:
        return CapabilityStatus(False, "未安装 ONNX Runtime GPU 运行依赖")
    except Exception:
        return CapabilityStatus(False, "ONNX Runtime CUDA 初始化失败")
    return CapabilityStatus(True)


def _detect_tensorrt(
    gpu: GpuStatus,
    load_module: Callable[[str], ModuleType],
) -> CapabilityStatus:
    if not gpu.available:
        return CapabilityStatus(False, gpu.reason or "NVIDIA GPU 不可用")
    try:
        tensorrt = load_module("tensorrt")
        logger = tensorrt.Logger(tensorrt.Logger.ERROR)
        tensorrt.Builder(logger)
    except ModuleNotFoundError:
        return CapabilityStatus(False, "未安装 TensorRT 运行依赖")
    except Exception:
        return CapabilityStatus(False, "TensorRT Builder 初始化失败")
    return CapabilityStatus(True)


def detect_capabilities(
    *,
    run_command: Callable[[list[str]], str] = _run_nvidia_smi,
    load_module: Callable[[str], ModuleType] = importlib.import_module,
    find_module: Callable[[str], object | None] = importlib.util.find_spec,
) -> SystemCapabilities:
    gpu = _detect_gpu(run_command)
    pytorch_cuda = _detect_pytorch(load_module)
    ultralytics = _detect_ultralytics(find_module)
    yolo = pytorch_cuda if not pytorch_cuda.available else ultralytics
    onnx_export = _detect_onnx_export(find_module)
    onnx_inference = _detect_onnx_inference(load_module)
    if not gpu.available and onnx_inference.available:
        onnx_inference = CapabilityStatus(False, gpu.reason)
    return SystemCapabilities(
        gpu=gpu,
        pytorch_cuda=pytorch_cuda,
        features=FeatureCapabilities(
            manual_annotation=CapabilityStatus(True),
            yolo_auto_annotation=yolo,
            model_training=pytorch_cuda,
            onnx_export=onnx_export,
            onnx_inference=onnx_inference,
            tensorrt=_detect_tensorrt(gpu, load_module),
        ),
    )
