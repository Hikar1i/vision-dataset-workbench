import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from ..inference import InferenceRunner
from ..models import InferenceModel, ModelArtifact, ModelInferenceRun, ModelProject, Task, User
from .authorization import Permission
from .models import ModelNotFound, ModelService, touch_model_project

IMAGE_LIMIT = 20 * 1024 * 1024
VIDEO_LIMIT = 500 * 1024 * 1024
SESSION_TTL = timedelta(hours=24)


class ModelInferenceError(ValueError):
    pass


class ModelInferenceNotFound(ModelInferenceError):
    pass


class ModelInferenceForbidden(ModelInferenceError):
    pass


class ModelInferenceConflict(ModelInferenceError):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class ModelInferenceService:
    def __init__(
        self, engine: Engine, workspace: Path, runner: InferenceRunner, models: ModelService
    ):
        self.workspace = workspace.resolve()
        self.runner = runner
        self.models = models
        self._session_factory = sessionmaker(engine, expire_on_commit=False)

    def _require_model(
        self, actor: User, model_id: str, permission: Permission
    ) -> None:
        try:
            model = self.models.get_model(actor, model_id)
            access = self.models.project_access(actor, model.model_project_id)
        except ModelNotFound as exc:
            raise ModelInferenceNotFound("可用模型不存在") from exc
        if not access.allows(permission):
            raise ModelInferenceForbidden(f"{permission} permission required")

    def current(self, actor: User, model_id: str) -> ModelInferenceRun | None:
        self._require_model(actor, model_id, "artifact.read")
        with self._session_factory() as database:
            self._model(database, model_id)
            run = database.scalar(
                select(ModelInferenceRun).where(
                    ModelInferenceRun.model_id == model_id,
                    ModelInferenceRun.created_by_id == actor.id,
                    ModelInferenceRun.saved_at.is_(None),
                    ModelInferenceRun.deleted_at.is_(None),
                )
            )
            if run:
                database.expunge(run)
            return run

    def saved(self, actor: User, model_id: str) -> list[ModelInferenceRun]:
        self._require_model(actor, model_id, "artifact.read")
        with self._session_factory() as database:
            self._model(database, model_id)
            rows = list(
                database.scalars(
                    select(ModelInferenceRun)
                    .where(
                        ModelInferenceRun.model_id == model_id,
                        ModelInferenceRun.saved_at.is_not(None),
                        ModelInferenceRun.deleted_at.is_(None),
                    )
                    .order_by(ModelInferenceRun.saved_at.desc())
                )
            )
            for row in rows:
                database.expunge(row)
            return rows

    def create(
        self,
        actor: User,
        model_id: str,
        input_type: str,
        artifact_format: str,
        upload: Path,
        original_name: str,
        parameters: dict[str, object],
        *,
        replace: bool,
    ) -> ModelInferenceRun:
        self._require_model(actor, model_id, "artifact.consume")
        self._require_model(actor, model_id, "task.execute")
        if input_type not in {"image", "video"} or artifact_format not in {
            "pt",
            "onnx",
            "engine",
        }:
            raise ModelInferenceError("unsupported inference input or format")
        limit = IMAGE_LIMIT if input_type == "image" else VIDEO_LIMIT
        if not upload.is_file() or upload.stat().st_size == 0:
            raise ModelInferenceError("上传文件为空")
        if upload.stat().st_size > limit:
            raise ModelInferenceError(f"文件超过 {limit // 1024 // 1024} MB 限制")
        now = _now()
        discarded_directory = None
        with self._session_factory() as database:
            model = self._model(database, model_id)
            previous = database.scalar(
                select(ModelInferenceRun).where(
                    ModelInferenceRun.model_id == model_id,
                    ModelInferenceRun.created_by_id == actor.id,
                    ModelInferenceRun.saved_at.is_(None),
                    ModelInferenceRun.deleted_at.is_(None),
                )
            )
            if previous and not replace:
                raise ModelInferenceConflict("已有未保存的推理会话，确认后可替换")
            if previous:
                if previous.status not in {"queued", "running"}:
                    discarded_directory = self._directory(previous)
                self._discard(database, previous, now)
            model_path, artifact_hash, fixed_size = self._model_path(
                database, model, artifact_format
            )
            normalized = self._parameters(parameters, fixed_size)
            run = ModelInferenceRun(
                id=str(uuid4()),
                model_id=model.id,
                source_model_sha256=model.sha256 or "",
                format=artifact_format,
                artifact_sha256=artifact_hash,
                created_by_id=actor.id,
                input_type=input_type,
                source_path="pending",
                parameters=json.dumps(normalized, ensure_ascii=False),
                statistics="{}",
                status="running" if input_type == "image" else "queued",
                last_accessed_at=now,
                expires_at=now + SESSION_TTL,
                created_at=now,
                started_at=now if input_type == "image" else None,
            )
            task = None
            if input_type == "video":
                project = database.get(ModelProject, model.model_project_id)
                task = Task(
                    id=str(uuid4()),
                    model_project_id=project.id if project else model.model_project_id,
                    submitted_by_id=actor.id,
                    type="infer_video",
                    payload=json.dumps({"run_id": run.id}, ensure_ascii=False),
                    created_at=now,
                    updated_at=now,
                )
                run.task_id = task.id
                database.add(task)
                database.flush()
            directory = self._directory(run)
            directory.mkdir(parents=True, exist_ok=True)
            suffix = Path(original_name).suffix.lower()[:12] or (
                ".jpg" if input_type == "image" else ".mp4"
            )
            source = directory / f"source{suffix}"
            shutil.move(str(upload), source)
            run.source_path = source.relative_to(self.workspace).as_posix()
            try:
                database.add(run)
                database.commit()
            except IntegrityError as exc:
                database.rollback()
                shutil.rmtree(directory, ignore_errors=True)
                raise ModelInferenceConflict("已有未保存的推理会话") from exc
            database.expunge(run)
        if discarded_directory:
            shutil.rmtree(discarded_directory, ignore_errors=True)
        if input_type == "image":
            try:
                self._infer_image(run.id, model, model_path, source, normalized)
            except Exception as exc:
                raise ModelInferenceConflict(str(exc)) from exc
            return self.get(actor, run.id)
        return run

    def get(self, actor: User, run_id: str) -> ModelInferenceRun:
        with self._session_factory() as database:
            run = self._run(database, run_id)
            if run.saved_at is None and run.created_by_id != actor.id and not actor.is_system_admin:
                raise ModelInferenceForbidden("无权访问该推理会话")
            if run.saved_at is not None:
                self._require_model(actor, run.model_id, "artifact.read")
            database.expunge(run)
            return run

    def touch(self, actor: User, run_id: str) -> ModelInferenceRun:
        with self._session_factory() as database:
            run = self._owned(database, actor, run_id)
            now = _now()
            run.last_accessed_at = now
            if run.saved_at is None:
                run.expires_at = now + SESSION_TTL
            database.commit()
            database.expunge(run)
            return run

    def save(self, actor: User, run_id: str) -> ModelInferenceRun:
        with self._session_factory() as database:
            run = self._owned(database, actor, run_id)
            model = self._model(database, run.model_id)
            self._require_model(actor, model.id, "task.execute")
            if run.status != "succeeded":
                raise ModelInferenceConflict("仅成功的推理结果可以保存")
            now = _now()
            run.saved_at = now
            run.expires_at = None
            touch_model_project(database, model.model_project_id, at=now)
            database.commit()
            database.expunge(run)
            return run

    def delete(self, actor: User, run_id: str) -> None:
        with self._session_factory() as database:
            run = self._owned(database, actor, run_id)
            was_saved = run.saved_at is not None
            model = self._model(database, run.model_id) if was_saved else None
            if was_saved:
                self._require_model(actor, run.model_id, "project.update")
            now = _now()
            self._discard(database, run, now)
            if model is not None:
                touch_model_project(database, model.model_project_id, at=now)
            database.commit()
            if run.status not in {"queued", "running"}:
                shutil.rmtree(self._directory(run), ignore_errors=True)

    def file(self, actor: User, run_id: str, kind: str) -> tuple[Path, str]:
        run = self.get(actor, run_id)
        relative = run.source_path if kind == "source" else run.result_path
        if kind not in {"source", "result"} or not relative:
            raise ModelInferenceNotFound("推理文件不存在")
        path = (self.workspace / relative).resolve()
        if not path.is_file() or not path.is_relative_to(self._directory(run)):
            raise ModelInferenceNotFound("推理文件不存在")
        return path, path.name

    def sweep_expired(self) -> int:
        now = _now()
        paths: list[Path] = []
        with self._session_factory() as database:
            rows = list(
                database.scalars(
                    select(ModelInferenceRun).where(
                        ModelInferenceRun.saved_at.is_(None),
                        ModelInferenceRun.deleted_at.is_(None),
                        ModelInferenceRun.expires_at < now,
                        ModelInferenceRun.status.in_(("succeeded", "failed", "canceled")),
                    )
                )
            )
            for run in rows:
                run.deleted_at = now
                paths.append(self._directory(run))
            database.commit()
        for path in paths:
            shutil.rmtree(path, ignore_errors=True)
        return len(paths)

    def _infer_image(self, run_id, model, model_path, source, parameters) -> None:
        started = _now()
        try:
            with Image.open(source) as image:
                image.verify()
            detections = self.runner.predict(
                model,
                model_path,
                source,
                [],
                float(parameters["confidence"]),
                float(parameters["iou"]),
                model_key=f"{model.id}:{model_path}",
                imgsz=int(parameters["image_size"]),
                max_det=int(parameters["max_det"]),
            )
            with Image.open(source) as opened:
                image = opened.convert("RGB")
            draw = ImageDraw.Draw(image)
            font = ImageFont.load_default(size=16)
            for item in detections:
                color = "#27a0b6"
                label = f"{item.label} {item.confidence or 0:.2f}"
                text_box = draw.textbbox((0, 0), label, font=font)
                text_width = text_box[2] - text_box[0]
                text_height = text_box[3] - text_box[1]
                label_top = max(0, round(item.y_min) - text_height - 8)
                draw.rectangle(
                    (item.x_min, item.y_min, item.x_max, item.y_max),
                    outline=color,
                    width=3,
                )
                draw.rectangle(
                    (item.x_min, label_top, item.x_min + text_width + 8, label_top + text_height + 6),
                    fill=color,
                )
                draw.text(
                    (item.x_min + 4, label_top + 3),
                    label,
                    fill="white",
                    font=font,
                )
            result = self._directory_id(model.id, run_id) / "result.jpg"
            image.save(result, quality=92)
            elapsed = max((_now() - started).total_seconds(), 0.0001)
            self._finish(run_id, result, {"detections": len(detections), "inference_seconds": elapsed})
        except Exception as exc:
            with self._session_factory() as database:
                run = database.get(ModelInferenceRun, run_id)
                if run:
                    run.status = "failed"
                    run.error = str(exc)[:2000]
                    run.finished_at = _now()
                    database.commit()
            raise

    def _finish(self, run_id: str, result: Path, statistics: dict[str, object]) -> None:
        now = _now()
        with self._session_factory() as database:
            run = database.get(ModelInferenceRun, run_id)
            if run is None:
                raise ModelInferenceNotFound("推理会话不存在")
            run.status = "succeeded"
            run.result_path = result.relative_to(self.workspace).as_posix()
            run.statistics = json.dumps(statistics, ensure_ascii=False)
            run.finished_at = now
            database.commit()

    def _model_path(self, database, model, artifact_format):
        if artifact_format == "pt":
            path = self.workspace / str(model.storage_path or "")
            if not path.is_file():
                raise ModelInferenceNotFound("模型文件不存在")
            return path, None, None
        artifact = database.scalar(
            select(ModelArtifact).where(
                ModelArtifact.model_id == model.id,
                ModelArtifact.format == artifact_format,
                ModelArtifact.status == "ready",
                ModelArtifact.deleted_at.is_(None),
            )
        )
        if artifact is None or not artifact.storage_path:
            raise ModelInferenceConflict("所选格式尚无可用转换产物")
        path = self.workspace / artifact.storage_path
        if not path.is_file():
            raise ModelInferenceNotFound("转换产物文件不存在")
        config = json.loads(artifact.export_config)
        fixed = None if config.get("dynamic") else int(config.get("imgsz") or 640)
        return path, artifact.sha256, fixed

    @staticmethod
    def _parameters(values, fixed_size):
        confidence = float(values.get("confidence", 0.25))
        iou = float(values.get("iou", 0.7))
        image_size = fixed_size or int(values.get("image_size", 640))
        max_det = int(values.get("max_det", 300))
        stride = int(values.get("stride", 1))
        if not 0 <= confidence <= 1 or not 0 <= iou <= 1:
            raise ModelInferenceError("置信度和 IOU 必须在 0 到 1 之间")
        if image_size < 32 or image_size > 8192 or image_size % 32:
            raise ModelInferenceError("图像尺寸必须为 32 到 8192 之间的 32 倍数")
        if not 1 <= max_det <= 3000 or not 1 <= stride <= 120:
            raise ModelInferenceError("最大检测数或视频步长超出范围")
        return {"confidence": confidence, "iou": iou, "image_size": image_size, "max_det": max_det, "stride": stride}

    def _discard(self, database, run, now):
        if run.task_id:
            task = database.get(Task, run.task_id)
            if task and task.status in {"queued", "running"}:
                task.cancel_requested = True
                if task.status == "queued":
                    task.status = "canceled"
                    task.finished_at = now
        run.deleted_at = now

    def _owned(self, database, actor, run_id):
        run = self._run(database, run_id)
        if run.created_by_id != actor.id and not actor.is_system_admin:
            raise ModelInferenceForbidden("无权管理该推理会话")
        return run

    @staticmethod
    def _run(database, run_id):
        run = database.get(ModelInferenceRun, run_id)
        if run is None or run.deleted_at is not None:
            raise ModelInferenceNotFound("推理会话不存在")
        return run

    @staticmethod
    def _model(database, model_id):
        model = database.get(InferenceModel, model_id)
        if model is None or model.deleted_at is not None or model.status != "ready":
            raise ModelInferenceNotFound("可用模型不存在")
        return model

    def _directory(self, run):
        return self._directory_id(run.model_id, run.id)

    def _directory_id(self, model_id, run_id):
        return (self.workspace / "models" / model_id / "inference" / run_id).resolve()
