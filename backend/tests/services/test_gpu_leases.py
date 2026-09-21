from datetime import datetime, timedelta

from vision_dataset_workbench.capabilities import GpuDevice
from vision_dataset_workbench.database import create_workspace_database, make_engine
from vision_dataset_workbench.services.gpu_leases import GpuLeaseService


DEVICES = (
    GpuDevice(0, "A4000", 16376, "GPU-a", "8.6"),
    GpuDevice(1, "RTX4000", 8192, "GPU-b", "7.5"),
)


def service(tmp_path, *, now):
    database_path = tmp_path / "db.sqlite3"
    create_workspace_database(database_path)
    engine = make_engine(database_path)
    return engine, GpuLeaseService(engine, devices=DEVICES, now=lambda: now[0])


def test_auto_acquire_uses_lowest_free_gpu_and_release_reuses_it(tmp_path):
    now = [datetime(2026, 9, 17, 8)]
    engine, leases = service(tmp_path, now=now)

    first = leases.acquire("evaluation", "one")
    second = leases.acquire("inference", "two")

    assert first and (first.gpu_index, first.gpu_uuid) == (0, "GPU-a")
    assert second and (second.gpu_index, second.gpu_uuid) == (1, "GPU-b")
    assert leases.acquire("conversion", "three") is None
    leases.release("evaluation", "one")
    replacement = leases.acquire("conversion", "three")
    assert replacement and replacement.gpu_uuid == "GPU-a"
    engine.dispose()


def test_fixed_index_uuid_renewal_and_expired_recovery(tmp_path):
    now = [datetime(2026, 9, 17, 8)]
    engine, leases = service(tmp_path, now=now)

    training = leases.acquire("training", "run-1", gpu_index=1)
    assert training and training.gpu_uuid == "GPU-b"
    assert leases.acquire("evaluation", "blocked", gpu_uuid="GPU-b") is None

    now[0] += timedelta(seconds=20)
    leases.renew("training", "run-1")
    assert leases.acquire("evaluation", "still-blocked", gpu_index=1) is None

    now[0] += timedelta(seconds=31)
    recovered = leases.acquire("evaluation", "recovered", gpu_uuid="GPU-b")
    assert recovered and recovered.gpu_index == 1
    engine.dispose()
