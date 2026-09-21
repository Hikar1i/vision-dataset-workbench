from collections.abc import Callable, Sequence
from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..capabilities import GpuDevice, _detect_gpu, _run_nvidia_smi
from ..models import GpuLease


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class GpuLeaseService:
    def __init__(
        self,
        engine: Engine,
        *,
        devices: Sequence[GpuDevice] | None = None,
        now: Callable[[], datetime] = _now,
        lease_seconds: int = 30,
    ):
        self._session_factory = sessionmaker(engine, expire_on_commit=False)
        self._devices = tuple(devices) if devices is not None else _detect_gpu(_run_nvidia_smi).devices
        self._now = now
        self._lease_seconds = lease_seconds

    def device(self, gpu_uuid: str) -> GpuDevice | None:
        return next((item for item in self._devices if item.uuid == gpu_uuid), None)

    def acquire(
        self,
        owner_type: str,
        owner_id: str,
        *,
        gpu_index: int | None = None,
        gpu_uuid: str | None = None,
    ) -> GpuLease | None:
        if gpu_index is not None and gpu_uuid is not None:
            raise ValueError("gpu_index and gpu_uuid are mutually exclusive")
        now = self._now()
        with self._session_factory() as database:
            database.connection().exec_driver_sql("BEGIN IMMEDIATE")
            database.execute(delete(GpuLease).where(GpuLease.expires_at < now))
            existing = database.scalar(
                select(GpuLease).where(
                    GpuLease.owner_type == owner_type,
                    GpuLease.owner_id == owner_id,
                )
            )
            if existing is not None:
                if gpu_index is not None and existing.gpu_index != gpu_index:
                    database.rollback()
                    return None
                if gpu_uuid is not None and existing.gpu_uuid != gpu_uuid:
                    database.rollback()
                    return None
                existing.expires_at = now + timedelta(seconds=self._lease_seconds)
                existing.updated_at = now
                database.commit()
                database.expunge(existing)
                return existing

            candidates = sorted(self._devices, key=lambda item: item.index)
            if gpu_index is not None:
                candidates = [item for item in candidates if item.index == gpu_index]
            if gpu_uuid is not None:
                candidates = [item for item in candidates if item.uuid == gpu_uuid]
            occupied = set(database.scalars(select(GpuLease.gpu_uuid)))
            device = next((item for item in candidates if item.uuid not in occupied), None)
            if device is None:
                database.rollback()
                return None
            lease = GpuLease(
                gpu_uuid=device.uuid,
                gpu_index=device.index,
                owner_type=owner_type,
                owner_id=owner_id,
                expires_at=now + timedelta(seconds=self._lease_seconds),
                created_at=now,
                updated_at=now,
            )
            database.add(lease)
            database.commit()
            database.expunge(lease)
            return lease

    def renew(
        self, owner_type: str, owner_id: str, *, database: Session | None = None
    ) -> None:
        now = self._now()
        if database is not None:
            lease = database.scalar(
                select(GpuLease).where(
                    GpuLease.owner_type == owner_type,
                    GpuLease.owner_id == owner_id,
                )
            )
            if lease is not None:
                lease.expires_at = now + timedelta(seconds=self._lease_seconds)
                lease.updated_at = now
            return
        with self._session_factory() as owned_database:
            self.renew(owner_type, owner_id, database=owned_database)
            owned_database.commit()

    def release(
        self, owner_type: str, owner_id: str, *, database: Session | None = None
    ) -> None:
        if database is not None:
            database.execute(
                delete(GpuLease).where(
                    GpuLease.owner_type == owner_type,
                    GpuLease.owner_id == owner_id,
                )
            )
            return
        with self._session_factory() as owned_database:
            self.release(owner_type, owner_id, database=owned_database)
            owned_database.commit()
