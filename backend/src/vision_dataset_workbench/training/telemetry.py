import csv
import platform
import subprocess
import time
from io import StringIO

import psutil

_cache: tuple[float, dict[str, object]] | None = None


def memory_level(percent: float) -> str:
    return "green" if percent < 60 else "orange" if percent < 85 else "red"


def training_telemetry(
    *, ttl: float = 2.0, now=time.monotonic, run=subprocess.run
) -> dict[str, object]:
    global _cache
    current = now()
    if _cache and 0 <= current - _cache[0] < ttl:
        return _cache[1]
    devices: list[dict[str, object]] = []
    reason = None
    try:
        result = run(
            [
                "nvidia-smi",
                "--query-gpu=index,name,memory.total,memory.used,utilization.gpu",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            check=True,
            text=True,
            timeout=3,
        )
        for row in csv.reader(StringIO(result.stdout)):
            total, used = int(float(row[2])), int(float(row[3]))
            percent = round(used / total * 100, 1) if total else 0
            devices.append(
                {
                    "index": int(row[0]),
                    "name": row[1].strip(),
                    "memory_total_mb": total,
                    "memory_used_mb": used,
                    "memory_percent": percent,
                    "utilization_percent": int(float(row[4])),
                    "level": memory_level(percent),
                }
            )
    except Exception:
        reason = "无法读取 NVIDIA GPU 实时状态"
    virtual = psutil.virtual_memory()
    payload = {
        "available": bool(devices),
        "reason": reason,
        "devices": devices,
        "host": {
            "hostname": platform.node(),
            "platform": platform.platform(),
            "cpu_count": psutil.cpu_count(),
            "memory_total_mb": round(virtual.total / 1024 / 1024),
            "memory_used_mb": round(virtual.used / 1024 / 1024),
        },
    }
    _cache = (current, payload)
    return payload
