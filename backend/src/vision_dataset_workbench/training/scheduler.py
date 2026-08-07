import hashlib
import json
import os
import signal
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import psutil
import yaml
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from ..models import (
    InferenceModel,
    ModelProject,
    ModelProjectTag,
    ModelProjectTagLink,
    TrainingMetric,
    TrainingModel,
    TrainingRun,
    TrainingTask,
)
from .events import validate_event
from .retention import cleanup_intermediate_checkpoints
from .state import aggregate_progress, aggregate_task_state
from .telemetry import training_telemetry


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TrainingScheduler:
    def __init__(
        self,
        engine: Engine,
        workspace: Path,
        *,
        worker_id: str,
        popen=subprocess.Popen,
        fake: bool | None = None,
    ):
        self.workspace = workspace.resolve()
        self.worker_id = worker_id
        self._session_factory = sessionmaker(engine, expire_on_commit=False)
        self._popen = popen
        self.fake = bool(os.environ.get("VDW_FAKE_TRAINING") == "1") if fake is None else fake

    def tick(self) -> None:
        self._monitor_active()
        self._start_available()

    def _monitor_active(self) -> None:
        with self._session_factory() as db:
            ids = list(
                db.scalars(
                    select(TrainingRun.id).where(TrainingRun.status.in_(("running", "canceling")))
                )
            )
        for run_id in ids:
            self._consume_events(run_id)
            with self._session_factory() as db:
                run = db.get(TrainingRun, run_id)
                if run is None or run.status not in {"running", "canceling"}:
                    continue
                if run.status == "canceling" and run.pid:
                    try:
                        os.kill(run.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
                alive = False
                if run.pid:
                    try:
                        process = psutil.Process(run.pid)
                        alive = process.is_running() and process.status() != psutil.STATUS_ZOMBIE
                    except psutil.Error:
                        pass
                if alive:
                    run.lease_expires_at = _now() + timedelta(seconds=30)
                    db.commit()
                    continue
                # The child may have completed between the first file read and the
                # liveness check. Consume once more so a just-flushed terminal line
                # wins over the generic "process exited" fallback.
                self._consume_events(run_id)
                db.refresh(run)
                if run.status not in {"running", "canceling"}:
                    continue
                status = "canceled" if run.status == "canceling" else "failed"
                self._finish_run(db, run, status, "training process exited without terminal event")
                db.commit()

    def _consume_events(self, run_id: str) -> None:
        with self._session_factory() as db:
            run = db.get(TrainingRun, run_id)
            if run is None:
                return
            events = self.workspace / run.storage_path / "events.jsonl"
            if not events.is_file():
                return
            with events.open("rb") as source:
                source.seek(run.event_offset)
                while line := source.readline():
                    if not line.endswith(b"\n"):
                        break
                    run.event_offset = source.tell()
                    try:
                        event = validate_event(
                            json.loads(line),
                            run_id=run.id,
                            token=run.run_token,
                            last_sequence=run.last_sequence,
                        )
                    except (ValueError, json.JSONDecodeError) as exc:
                        run.warning = str(exc)[:2000]
                        continue
                    run.last_sequence = int(event["sequence"])
                    kind = str(event["type"])
                    model = db.get(TrainingModel, run.training_model_id)
                    assert model
                    if kind == "started":
                        run.pid = int(event.get("pid") or run.pid or 0)
                    elif kind == "epoch_end":
                        epoch = int(event["epoch"])
                        metrics = event.get("metrics") or {}
                        row = db.get(TrainingMetric, (run.id, epoch)) or TrainingMetric(
                            training_run_id=run.id, epoch=epoch
                        )
                        for source_key, target in (
                            ("box_loss", "box_loss"),
                            ("cls_loss", "cls_loss"),
                            ("dfl_loss", "dfl_loss"),
                            ("learning_rate", "learning_rate"),
                            ("precision", "precision"),
                            ("recall", "recall"),
                            ("map50", "map50"),
                            ("map50_95", "map50_95"),
                        ):
                            setattr(row, target, metrics.get(source_key))
                        db.add(row)
                        run.current_epoch = max(run.current_epoch, epoch)
                        run.progress = min(100, epoch / run.target_epochs * 100)
                        model.progress = run.progress
                    elif kind == "artifact":
                        directory = Path(run.storage_path)
                        run.best_path = (
                            (directory / str(event["best"])).as_posix()
                            if event.get("best")
                            else None
                        )
                        run.last_path = (
                            (directory / str(event["last"])).as_posix()
                            if event.get("last")
                            else None
                        )
                    elif kind == "warning":
                        run.warning = str(event.get("message") or "training warning")[:2000]
                    elif kind == "failed":
                        self._finish_run(
                            db, run, "failed", str(event.get("error") or "training failed")
                        )
                    elif kind == "completed":
                        try:
                            self._publish(db, run, model)
                            self._finish_run(db, run, "succeeded", None)
                        except Exception as exc:
                            self._finish_run(db, run, "failed", str(exc))
                db.commit()

    def _start_available(self) -> None:
        with self._session_factory() as db:
            active_gpus = set(
                db.scalars(
                    select(TrainingRun.gpu_index).where(
                        TrainingRun.status.in_(("running", "canceling"))
                    )
                )
            )
            queued = list(
                db.scalars(
                    select(TrainingRun)
                    .where(TrainingRun.status == "queued")
                    .order_by(TrainingRun.enqueued_at, TrainingRun.id)
                )
            )
            selected: list[str] = []
            for run in queued:
                if run.gpu_index in active_gpus:
                    continue
                model = db.get(TrainingModel, run.training_model_id)
                assert model
                earlier = db.scalar(
                    select(TrainingModel.id).where(
                        TrainingModel.training_task_id == model.training_task_id,
                        TrainingModel.gpu_index == model.gpu_index,
                        TrainingModel.queue_order < model.queue_order,
                        TrainingModel.status.in_(("draft", "queued", "running", "canceling")),
                    )
                )
                if earlier:
                    continue
                run.status = "running"
                run.started_at = _now()
                run.worker_id = self.worker_id
                run.lease_expires_at = _now() + timedelta(seconds=30)
                model.status = "running"
                model.started_at = model.started_at or _now()
                task = db.get(TrainingTask, model.training_task_id)
                task.status = "running"
                task.started_at = task.started_at or _now()
                active_gpus.add(run.gpu_index)
                selected.append(run.id)
            db.commit()
        for run_id in selected:
            try:
                self._spawn(run_id)
            except Exception as exc:
                with self._session_factory() as db:
                    run = db.get(TrainingRun, run_id)
                    if run:
                        self._finish_run(db, run, "start_failed", str(exc))
                        db.commit()

    def _spawn(self, run_id: str) -> None:
        with self._session_factory() as db:
            run = db.get(TrainingRun, run_id)
            assert run
            model = db.get(TrainingModel, run.training_model_id)
            assert model
            task = db.get(TrainingTask, model.training_task_id)
            assert task
            dataset = json.loads(model.dataset_snapshot)
            template = json.loads(model.template_snapshot)
            base = json.loads(model.base_model_snapshot)
            base_path = self.workspace / base["storage_path"]
            if run.kind == "resume":
                previous = db.scalar(
                    select(TrainingRun).where(
                        TrainingRun.training_model_id == model.id,
                        TrainingRun.attempt_no == run.attempt_no - 1,
                    )
                )
                base_path = self.workspace / previous.last_path
            elif model.continuation_of_id:
                previous = db.scalar(
                    select(TrainingRun)
                    .where(
                        TrainingRun.training_model_id == model.continuation_of_id,
                        TrainingRun.status == "succeeded",
                    )
                    .order_by(TrainingRun.attempt_no.desc())
                )
                chosen = (
                    previous.best_path
                    if model.continuation_checkpoint == "best"
                    else previous.last_path
                )
                base_path = self.workspace / chosen
            directory = self.workspace / run.storage_path
            directory.mkdir(parents=True, exist_ok=True)
            dataset_directory = (self.workspace / dataset["storage_path"]).resolve()
            source_yaml = dataset_directory / "dataset.yaml"
            dataset_config = yaml.safe_load(source_yaml.read_text(encoding="utf-8"))
            if not isinstance(dataset_config, dict):
                raise ValueError("dataset.yaml must contain a mapping")
            configured_root = Path(str(dataset_config.get("path") or "."))
            if not configured_root.is_absolute():
                configured_root = dataset_directory / configured_root
            dataset_config["path"] = str(configured_root.resolve())
            run_yaml = directory / "dataset.yaml"
            run_yaml.write_text(
                yaml.safe_dump(dataset_config, allow_unicode=True, sort_keys=False),
                encoding="utf-8",
            )
            spec = {
                "run_id": run.id,
                "token": run.run_token,
                "gpu_index": run.gpu_index,
                "dataset_yaml": str(run_yaml),
                "base_model": str(base_path),
                "parameters": template["parameters"],
                "output": str(directory),
                "fake": self.fake,
                "resume": run.kind == "resume",
            }
            spec_path, events_path, log_path = (
                directory / "spec.json",
                directory / "events.jsonl",
                directory / "train.log",
            )
            spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            cache_directory = self.workspace / "cache" / "ultralytics"
            cache_directory.mkdir(parents=True, exist_ok=True)
            log = log_path.open("ab")
            process = self._popen(
                [
                    sys.executable,
                    "-m",
                    "vision_dataset_workbench.training.process",
                    "--spec",
                    str(spec_path),
                    "--events",
                    str(events_path),
                ],
                stdout=log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=cache_directory,
            )
            log.close()
            run.pid = process.pid
            run.host_snapshot = json.dumps(training_telemetry(), ensure_ascii=False)
            db.commit()

    def _finish_run(self, db, run: TrainingRun, status: str, error: str | None) -> None:
        now = _now()
        run.status = status
        run.error = error[:2000] if error else None
        run.finished_at = now
        run.lease_expires_at = None
        model = db.get(TrainingModel, run.training_model_id)
        assert model
        model.status = status
        model.finished_at = now
        model.progress = 100 if status == "succeeded" else run.progress
        try:
            cleanup_intermediate_checkpoints(self.workspace / run.storage_path)
        except Exception as exc:
            run.warning = f"checkpoint cleanup failed: {exc}"[:2000]
        task = db.get(TrainingTask, model.training_task_id)
        assert task
        models = list(
            db.scalars(
                select(TrainingModel).where(
                    TrainingModel.training_task_id == task.id, TrainingModel.deleted_at.is_(None)
                )
            )
        )
        task.progress = aggregate_progress(models)
        task.status = aggregate_task_state(models)
        task.updated_at = now
        if task.status not in {"queued", "running", "canceling"}:
            task.finished_at = now

    def _publish(self, db, run: TrainingRun, model: TrainingModel) -> None:
        if not run.best_path:
            raise RuntimeError("training did not produce best.pt")
        source = self.workspace / run.best_path
        if not source.is_file():
            raise RuntimeError("best.pt is missing")
        task = db.get(TrainingTask, model.training_task_id)
        assert task
        project = db.scalar(select(ModelProject).where(ModelProject.training_task_id == task.id))
        now = _now()
        if project is None:
            project = ModelProject(
                id=str(uuid4()),
                name=task.name,
                name_normalized=task.name.lower(),
                description=task.description,
                series_type="training",
                training_task_id=task.id,
                created_by_id=task.created_by_id,
                created_at=now,
                updated_at=now,
            )
            db.add(project)
            db.flush()
            tag = db.scalar(
                select(ModelProjectTag).where(ModelProjectTag.name_normalized == "训练")
            )
            if tag is None:
                tag = ModelProjectTag(
                    id=str(uuid4()), name="训练", name_normalized="训练", created_at=now
                )
                db.add(tag)
                db.flush()
            db.add(ModelProjectTagLink(model_project_id=project.id, tag_id=tag.id))
        published = db.scalar(
            select(InferenceModel).where(InferenceModel.training_model_id == model.id)
        )
        if published is None:
            published = InferenceModel(
                id=str(uuid4()),
                model_project_id=project.id,
                training_model_id=model.id,
                name=model.name,
                model_code=model.artifact_code,
                kind="yolo",
                description=model.description,
                parameters=model.template_snapshot,
                status="ready",
                source_name=f"{model.artifact_code}.pt",
                created_by_id=task.created_by_id,
                created_at=now,
                updated_at=now,
            )
            db.add(published)
            db.flush()
        target_dir = self.workspace / "models" / published.id
        target_dir.mkdir(parents=True, exist_ok=True)
        target, staged = target_dir / f"{model.artifact_code}.pt", target_dir / ".publishing.pt"
        with source.open("rb") as reader, staged.open("wb") as writer:
            while data := reader.read(1024 * 1024):
                writer.write(data)
            writer.flush()
            os.fsync(writer.fileno())
        os.replace(staged, target)
        published.storage_path = target.relative_to(self.workspace).as_posix()
        published.file_size = target.stat().st_size
        with target.open("rb") as stream:
            published.sha256 = hashlib.file_digest(stream, "sha256").hexdigest()
        published.parameters = model.template_snapshot
        published.version += 1 if published.version else 0
        published.updated_at = now
        published.deleted_at = None
        published.status = "ready"
