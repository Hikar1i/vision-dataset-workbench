import argparse
import hashlib
import json
import os
import queue
import re
import shutil
import signal
import subprocess
import threading
import time
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import delete, func, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .config import RuntimeSettings
from .database import make_engine
from .dataset_export_task import DatasetExportTaskCanceled, execute_dataset_export
from .media import MediaMetadata, MediaToolError, normalize_remote_url, probe_video, ytdlp_base_args
from .inference import InferenceRunner, InferenceUnavailable
from .models import (
    DatasetExport,
    Frame,
    FrameAnnotation,
    InferenceModel,
    ProjectLabel,
    SamplingPlan,
    Task,
    Video,
)
from .sampling import SamplingEstimate, ffmpeg_select, source_frame_index
from .services.labels import automatic_label_color, normalize_label_name
from .storage.browser import VIDEO_EXTENSIONS
from .storage.locator import WorkspaceLocator, default_locator_path
from .storage.paths import HomePathResolver, UnsafePathError

LIMITS = {
    "copy_video": 2,
    "download_video": 2,
    "extract_frames": 2,
    "import_model": 1,
    "auto_annotate": 2,
    "export_dataset": 1,
}
LEASE_SECONDS = 30
COPY_CHUNK_SIZE = 1024 * 1024


class TaskCanceled(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def download_command(
    settings: RuntimeSettings, url: str, output_template: Path
) -> list[str]:
    return [
        *ytdlp_base_args(settings),
        "--no-playlist",
        "--newline",
        "--progress",
        "--progress-template",
        "download:vdw-progress:%(progress._percent_str)s",
        "--format",
        "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best",
        "--merge-output-format",
        "mp4",
        "--socket-timeout",
        "30",
        "--retries",
        "5",
        "--fragment-retries",
        "5",
        "--retry-sleep",
        "3",
        "--write-info-json",
        "--write-thumbnail",
        "--convert-thumbnails",
        "jpg",
        "--output",
        str(output_template),
        "--",
        normalize_remote_url(url),
    ]


class TaskWorker:
    def __init__(
        self,
        engine: Engine,
        settings: RuntimeSettings,
        workspace: Path,
        *,
        probe=probe_video,
        popen=subprocess.Popen,
        run=subprocess.run,
        now=_utc_now,
        worker_id: str | None = None,
        inference_runner: InferenceRunner | None = None,
    ):
        self.engine = engine
        self.settings = settings
        self.workspace = workspace.resolve()
        self._probe = probe
        self._popen = popen
        self._run = run
        self._now = now
        self.worker_id = worker_id or str(uuid4())
        self._inference_runner = inference_runner or InferenceRunner()
        self._session_factory = sessionmaker(engine, expire_on_commit=False)
        self._executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="vdw-task")
        self._futures: dict[str, Future[None]] = {}
        self._stop = threading.Event()

    def claim_available(self) -> list[Task]:
        now = self._now()
        with self._session_factory() as database:
            database.connection().exec_driver_sql("BEGIN IMMEDIATE")
            expired = database.scalars(
                select(Task).where(
                    Task.status == "running",
                    Task.lease_expires_at.is_not(None),
                    Task.lease_expires_at < now,
                )
            ).all()
            for task in expired:
                task.status = "queued"
                task.lease_owner = None
                task.lease_expires_at = None
                task.cancel_requested = False
                task.updated_at = now

            running = database.scalars(
                select(Task).where(Task.status == "running")
            ).all()
            type_counts = Counter(task.type for task in running)
            user_counts = Counter((task.type, task.submitted_by_id) for task in running)
            queued = database.scalars(
                select(Task)
                .where(Task.status == "queued")
                .order_by(Task.created_at, Task.id)
            ).all()
            claimed: list[Task] = []
            for task in queued:
                if type_counts[task.type] >= LIMITS[task.type]:
                    continue
                if user_counts[(task.type, task.submitted_by_id)] >= 1:
                    continue
                task.status = "running"
                task.started_at = task.started_at or now
                task.updated_at = now
                task.lease_owner = self.worker_id
                task.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
                task.attempts += 1
                type_counts[task.type] += 1
                user_counts[(task.type, task.submitted_by_id)] += 1
                claimed.append(task)
            database.commit()
            for task in claimed:
                database.expunge(task)
            return claimed

    def execute_task(self, task_id: str) -> None:
        task_temp = self.workspace / "tmp" / task_id
        self._remove_task_temp(task_temp)
        task_temp.mkdir(parents=True)
        try:
            with self._session_factory() as database:
                task = database.get(Task, task_id)
                if task is None or task.status != "running":
                    return
                task_type = task.type
            if self._cancel_requested(task_id):
                raise TaskCanceled("task canceled")
            if task_type == "copy_video":
                self._execute_copy(task_id, task_temp)
            elif task_type == "download_video":
                self._execute_download(task_id, task_temp)
            elif task_type == "extract_frames":
                self._execute_extract(task_id, task_temp)
            elif task_type == "import_model":
                self._execute_import_model(task_id, task_temp)
            elif task_type == "auto_annotate":
                self._execute_auto_annotate(task_id)
            elif task_type == "export_dataset":
                execute_dataset_export(
                    self._session_factory,
                    self.workspace,
                    task_id,
                    task_temp,
                    self._now,
                    self._heartbeat,
                    self._cancel_requested,
                )
            else:
                raise RuntimeError("unsupported task type")
        except (TaskCanceled, DatasetExportTaskCanceled):
            self._finish_canceled(task_id)
        except Exception as exc:
            self._finish_failed(task_id, exc)
        finally:
            self._remove_task_temp(task_temp)

    def _execute_copy(self, task_id: str, task_temp: Path) -> None:
        task, video, payload = self._load_task(task_id)
        source_relative = str(payload.get("source_path") or "")
        resolver = HomePathResolver(self.settings.home)
        source = resolver.resolve_existing(source_relative)
        if source == self.workspace or source.is_relative_to(self.workspace):
            raise UnsafePathError("managed workspace is not an import source")
        if not source.is_file() or source.suffix.lower() not in VIDEO_EXTENSIONS:
            raise MediaToolError("source is not a supported video file")

        copied = task_temp / source.name
        total = source.stat().st_size
        written = 0
        digest = hashlib.sha256()
        last_update = 0.0
        with source.open("rb") as reader, copied.open("xb") as writer:
            while chunk := reader.read(COPY_CHUNK_SIZE):
                writer.write(chunk)
                digest.update(chunk)
                written += len(chunk)
                current = time.monotonic()
                if current - last_update >= 1 or written == total:
                    self._heartbeat(task_id, round(written * 100 / total) if total else 100)
                    last_update = current
                if self._cancel_requested(task_id):
                    raise TaskCanceled("task canceled")

        content_hash = digest.hexdigest()
        if self._local_duplicate(video, content_hash):
            self._finish_duplicate(task_id, "same video content already exists")
            return
        metadata = self._probe(copied)
        thumbnail = self._make_thumbnail(copied, task_temp / f"{video.id}.jpg")
        self._publish(
            task,
            video,
            copied,
            metadata,
            thumbnail=thumbnail,
            content_sha256=content_hash,
        )

    def _execute_import_model(self, task_id: str, task_temp: Path) -> None:
        with self._session_factory() as database:
            task = database.get(Task, task_id)
            if task is None or task.status != "running":
                raise MediaToolError("active model import task not found")
            payload = json.loads(task.payload)
            model = database.get(InferenceModel, str(payload.get("model_id") or ""))
            if model is None or model.status != "copying":
                raise MediaToolError("model import target not found")
            model_id = model.id
        resolver = HomePathResolver(self.settings.home)
        source = resolver.resolve_existing(str(payload.get("source_path") or ""))
        if source == self.workspace or source.is_relative_to(self.workspace):
            raise UnsafePathError("managed workspace is not an import source")
        staged = task_temp / "model"
        copied_path = staged / source.name if source.is_file() else staged
        if source.is_file():
            staged.mkdir()
            self._copy_file_with_progress(task_id, source, copied_path, source.stat().st_size, 0)
        else:
            files = [
                path
                for path in source.rglob("*")
                if path.is_file()
                and not path.is_symlink()
                and path.resolve().is_relative_to(resolver.home)
                and not path.resolve().is_relative_to(self.workspace)
            ]
            total = sum(path.stat().st_size for path in files)
            copied = 0
            staged.mkdir()
            for path in files:
                destination = staged / path.relative_to(source)
                destination.parent.mkdir(parents=True, exist_ok=True)
                copied = self._copy_file_with_progress(
                    task_id, path, destination, total, copied
                )
        target = self.workspace / "models" / model_id
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            raise MediaToolError("model storage target already exists")
        os.replace(staged, target)
        relative = target / source.name if source.is_file() else target
        now = self._now()
        with self._session_factory() as database:
            model = database.get(InferenceModel, model_id)
            task = database.get(Task, task_id)
            if model is None or task is None:
                raise MediaToolError("model import resources disappeared")
            model.status = "ready"
            model.storage_path = relative.relative_to(self.workspace).as_posix()
            model.error = None
            model.updated_at = now
            task.status = "succeeded"
            task.progress = 100
            task.result = json.dumps({"outcome": "imported", "model_id": model_id})
            task.error = None
            task.finished_at = now
            task.updated_at = now
            task.lease_owner = None
            task.lease_expires_at = None
            database.commit()

    def _copy_file_with_progress(
        self,
        task_id: str,
        source: Path,
        destination: Path,
        total: int,
        copied: int,
    ) -> int:
        with source.open("rb") as reader, destination.open("xb") as writer:
            while chunk := reader.read(COPY_CHUNK_SIZE):
                writer.write(chunk)
                copied += len(chunk)
                self._heartbeat(task_id, min(99, round(copied * 100 / total)) if total else 99)
                if self._cancel_requested(task_id):
                    raise TaskCanceled("task canceled")
        return copied

    def _execute_auto_annotate(self, task_id: str) -> None:
        with self._session_factory() as database:
            task = database.get(Task, task_id)
            if task is None or task.status != "running" or task.video_id is None:
                raise MediaToolError("active auto annotation task not found")
            payload = json.loads(task.payload)
            video = database.get(Video, task.video_id)
            model = database.get(InferenceModel, str(payload.get("model_id") or ""))
            if video is None or model is None or model.status != "ready" or not model.storage_path:
                raise MediaToolError("auto annotation resources not ready")
            frames = list(
                database.scalars(
                    select(Frame)
                    .where(Frame.video_id == video.id, Frame.enabled.is_(True))
                    .order_by(Frame.sequence)
                )
            )
            if not frames:
                raise MediaToolError("video has no enabled sampled frames")
            if model.kind == "grounding_dino" and not payload.get("categories"):
                payload["categories"] = list(
                    database.scalars(
                        select(ProjectLabel.name).where(
                            ProjectLabel.project_id == video.project_id,
                            ProjectLabel.enabled.is_(True),
                        )
                    )
                )
            database.expunge(video)
            database.expunge(model)
            for frame in frames:
                database.expunge(frame)
        model_path = self._managed_model_path(model)
        total_annotations = 0
        for index, frame in enumerate(frames, start=1):
            if self._cancel_requested(task_id):
                raise TaskCanceled("task canceled")
            image_path = self._managed_frame_path(video, frame)
            try:
                detections = self._inference_runner.predict(
                    model,
                    model_path,
                    image_path,
                    list(payload.get("categories") or []),
                    float(payload.get("confidence", 0.25)),
                    float(payload.get("iou", 0.45)),
                )
            except InferenceUnavailable as exc:
                raise MediaToolError(str(exc)) from exc
            total_annotations += self._store_auto_detections(
                video,
                frame.id,
                detections,
                overwrite=bool(payload.get("overwrite", False)),
            )
            self._heartbeat(task_id, round(index * 100 / len(frames)))
        now = self._now()
        with self._session_factory() as database:
            task = database.get(Task, task_id)
            if task is None:
                raise MediaToolError("auto annotation task disappeared")
            task.status = "succeeded"
            task.progress = 100
            task.result = json.dumps(
                {"outcome": "annotated", "frames": len(frames), "annotations": total_annotations}
            )
            task.error = None
            task.finished_at = now
            task.updated_at = now
            task.lease_owner = None
            task.lease_expires_at = None
            database.commit()

    def _managed_model_path(self, model: InferenceModel) -> Path:
        try:
            path = (self.workspace / str(model.storage_path)).resolve(strict=True)
        except OSError as exc:
            raise MediaToolError("model file not found") from exc
        root = (self.workspace / "models" / model.id).resolve()
        if not path.is_relative_to(root):
            raise MediaToolError("model file not found")
        return path

    def _managed_frame_path(self, video: Video, frame: Frame) -> Path:
        try:
            path = (self.workspace / frame.file_path).resolve(strict=True)
        except OSError as exc:
            raise MediaToolError("frame file not found") from exc
        root = (
            self.workspace
            / "projects"
            / video.project_id
            / "frames"
            / video.short_code
        ).resolve()
        if not path.is_file() or not path.is_relative_to(root):
            raise MediaToolError("frame file not found")
        return path

    def _store_auto_detections(
        self,
        video: Video,
        frame_id: str,
        detections,
        *,
        overwrite: bool,
    ) -> int:
        valid = []
        for detection in detections:
            name = normalize_label_name(detection.label)
            bounds = {
                "x_min": max(0, min(video.width, round(detection.x_min))),
                "y_min": max(0, min(video.height, round(detection.y_min))),
                "x_max": max(0, min(video.width, round(detection.x_max))),
                "y_max": max(0, min(video.height, round(detection.y_max))),
            }
            if bounds["x_max"] - bounds["x_min"] >= 2 and bounds["y_max"] - bounds["y_min"] >= 2:
                valid.append((detection, name, bounds))
        if not valid and not overwrite:
            return 0
        now = self._now()
        with self._session_factory() as database:
            frame = database.get(Frame, frame_id)
            if frame is None or frame.video_id != video.id:
                raise MediaToolError("frame disappeared during auto annotation")
            names = {item[1] for item in valid}
            labels = {
                item.name_normalized: item
                for item in database.scalars(
                    select(ProjectLabel).where(ProjectLabel.project_id == video.project_id)
                )
            }
            last_order = database.scalar(
                select(func.max(ProjectLabel.sort_order)).where(
                    ProjectLabel.project_id == video.project_id
                )
            )
            next_order = 0 if last_order is None else last_order + 1
            for name in sorted(names - labels.keys()):
                label = ProjectLabel(
                    id=str(uuid4()),
                    project_id=video.project_id,
                    name=name,
                    name_normalized=name,
                    description_zh="",
                    color=automatic_label_color(name),
                    sort_order=next_order,
                    enabled=True,
                    version=1,
                    created_at=now,
                    updated_at=now,
                )
                next_order += 1
                database.add(label)
                labels[name] = label
            database.flush()
            if overwrite:
                database.execute(
                    delete(FrameAnnotation).where(FrameAnnotation.frame_id == frame_id)
                )
                first_annotation_order = 0
            else:
                last_annotation_order = database.scalar(
                    select(func.max(FrameAnnotation.sort_order)).where(
                        FrameAnnotation.frame_id == frame_id
                    )
                )
                first_annotation_order = (
                    0 if last_annotation_order is None else last_annotation_order + 1
                )
            database.add_all(
                [
                    FrameAnnotation(
                        id=str(uuid4()),
                        frame_id=frame_id,
                        label_id=labels[name].id,
                        **bounds,
                        source="model",
                        confidence=max(0.0, min(1.0, detection.confidence)),
                        sort_order=first_annotation_order + offset,
                        created_at=now,
                    )
                    for offset, (detection, name, bounds) in enumerate(valid)
                ]
            )
            frame.annotation_revision += 1
            database.commit()
        return len(valid)

    def _execute_download(self, task_id: str, task_temp: Path) -> None:
        task, video, payload = self._load_task(task_id)
        url = normalize_remote_url(str(payload.get("url") or ""))
        command = download_command(self.settings, url, task_temp / f"{video.id}.%(ext)s")
        process = self._popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        lines: queue.Queue[str] = queue.Queue()

        def read_output() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line.rstrip())

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        recent: list[str] = []
        while process.poll() is None or not lines.empty():
            try:
                line = lines.get(timeout=0.25)
                recent.append(line)
                recent = recent[-20:]
                match = re.search(r"vdw-progress:\s*([0-9.]+)%", line)
                if match:
                    self._heartbeat(task_id, min(99, round(float(match.group(1)))))
            except queue.Empty:
                self._heartbeat(task_id, None)
            if self._cancel_requested(task_id):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                raise TaskCanceled("task canceled")
        reader.join(timeout=1)
        if process.returncode != 0:
            raise MediaToolError("\n".join(recent[-5:]) or "yt-dlp download failed")

        info_files = list(task_temp.glob("*.info.json"))
        if not info_files:
            raise MediaToolError("yt-dlp did not write metadata")
        info = json.loads(info_files[0].read_text(encoding="utf-8"))
        media_files = [
            path
            for path in task_temp.iterdir()
            if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS
        ]
        if not media_files:
            raise MediaToolError("yt-dlp did not produce a video file")
        downloaded = max(media_files, key=lambda path: path.stat().st_size)
        extractor = str(info.get("extractor_key") or info.get("extractor") or "generic")
        external_id = str(info.get("id") or "").strip()
        if not external_id:
            raise MediaToolError("yt-dlp returned an item without an id")
        if self._remote_duplicate(video, extractor, external_id):
            self._finish_duplicate(task_id, "same remote video already exists")
            return
        metadata = self._probe(downloaded)
        thumbnail = next(iter(task_temp.glob(f"{video.id}.jpg")), None)
        video.title = str(info.get("title") or video.title)[:512]
        video.source_url = normalize_remote_url(
            str(info.get("webpage_url") or info.get("original_url") or url)
        )
        video.extractor = extractor
        video.external_id = external_id
        self._publish(task, video, downloaded, metadata, thumbnail=thumbnail)

    def _execute_extract(self, task_id: str, task_temp: Path) -> None:
        task, video, payload = self._load_task(task_id)
        requested_version = int(payload.get("sampling_plan_version") or 0)
        with self._session_factory() as database:
            plan = database.scalar(
                select(SamplingPlan).where(SamplingPlan.video_id == video.id)
            )
            if plan is None or plan.version != requested_version:
                raise MediaToolError("sampling plan changed; create a new extraction task")
            database.expunge(plan)
        if video.status != "ready" or not video.file_path:
            raise MediaToolError("video is not ready for extraction")
        try:
            video_path = (self.workspace / video.file_path).resolve(strict=True)
        except OSError as exc:
            raise MediaToolError("video file not found") from exc
        videos_root = (
            self.workspace / "projects" / video.project_id / "videos"
        ).resolve()
        if not video_path.is_file() or not video_path.is_relative_to(videos_root):
            raise MediaToolError("video file not found")

        estimate = SamplingEstimate(
            mode=plan.mode,
            parameters=json.loads(plan.parameters),
            computed_interval=plan.computed_interval,
            expected_frames=plan.expected_frames,
        )
        staged_frames = task_temp / "frames"
        staged_frames.mkdir()
        extension = plan.output_format
        quality_args = (
            ["-q:v", str(plan.output_quality)]
            if extension == "jpg"
            else ["-compression_level", str(plan.output_quality)]
        )
        output_pattern = staged_frames / (
            f"{video.short_code}_frame_%06d.{extension}"
        )
        command = [
            "ffmpeg",
            "-hide_banner",
            "-nostdin",
            "-i",
            str(video_path),
            "-vf",
            f"select={ffmpeg_select(estimate, video.total_frames)}",
            "-vsync",
            "vfr",
            "-threads",
            "2",
            *quality_args,
            "-progress",
            "pipe:1",
            "-nostats",
            "-y",
            str(output_pattern),
        ]
        process = self._popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        lines: queue.Queue[str] = queue.Queue()

        def read_output() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                lines.put(line.rstrip())

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        recent: list[str] = []
        last_update = 0.0
        while process.poll() is None or reader.is_alive() or not lines.empty():
            try:
                line = lines.get(timeout=0.25)
                recent.append(line)
                recent = recent[-20:]
                match = re.match(r"frame=\s*(\d+)", line)
                if match:
                    extracted = int(match.group(1))
                    progress = min(
                        99,
                        round(extracted * 100 / plan.expected_frames),
                    )
                    now = time.monotonic()
                    if now - last_update >= 1 or progress >= 99:
                        self._heartbeat(task_id, progress)
                        last_update = now
            except queue.Empty:
                now = time.monotonic()
                if now - last_update >= 1:
                    self._heartbeat(task_id, None)
                    last_update = now
            if self._cancel_requested(task_id):
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                raise TaskCanceled("task canceled")
        reader.join(timeout=1)
        if process.returncode != 0:
            raise MediaToolError("\n".join(recent[-5:]) or "ffmpeg extraction failed")
        if self._cancel_requested(task_id):
            raise TaskCanceled("task canceled")

        files = sorted(staged_frames.glob(f"*.{extension}"))
        if not files or any(not path.is_file() or path.stat().st_size == 0 for path in files):
            raise MediaToolError("ffmpeg did not produce valid frame files")
        self._publish_frames(
            task,
            video,
            plan,
            estimate,
            staged_frames,
            files,
        )

    def _publish_frames(
        self,
        task: Task,
        video: Video,
        plan: SamplingPlan,
        estimate: SamplingEstimate,
        staged_frames: Path,
        files: list[Path],
    ) -> None:
        target = (
            self.workspace
            / "projects"
            / video.project_id
            / "frames"
            / video.short_code
        )
        target.parent.mkdir(parents=True, exist_ok=True)
        backup = staged_frames.parent / "previous-frames"
        with self._session_factory() as database:
            current = database.get(SamplingPlan, plan.id)
            if current is None or current.version != plan.version:
                raise MediaToolError("sampling plan changed; create a new extraction task")
        if target.exists():
            os.replace(target, backup)
        os.replace(staged_frames, target)
        now = self._now()
        try:
            with self._session_factory() as database:
                stored_plan = database.get(SamplingPlan, plan.id)
                stored_task = database.get(Task, task.id)
                if (
                    stored_plan is None
                    or stored_plan.version != plan.version
                    or stored_task is None
                ):
                    raise MediaToolError("sampling task resources changed")
                generation = stored_plan.generation + 1
                database.execute(delete(Frame).where(Frame.video_id == video.id))
                for index, source in enumerate(files):
                    source_index = source_frame_index(
                        estimate,
                        min(index, estimate.expected_frames - 1),
                        video.total_frames,
                    )
                    destination = target / source.name
                    database.add(
                        Frame(
                            id=str(uuid4()),
                            video_id=video.id,
                            generation=generation,
                            sequence=index + 1,
                            source_frame_index=source_index,
                            time_offset=source_index / video.fps,
                            file_path=destination.relative_to(self.workspace).as_posix(),
                            enabled=True,
                            created_at=now,
                        )
                    )
                stored_plan.applied_version = stored_plan.version
                stored_plan.generation = generation
                stored_plan.extracted_frames = len(files)
                stored_plan.enabled_frames = len(files)
                stored_plan.frame_revision = 1
                stored_plan.updated_at = now
                stored_task.status = "succeeded"
                stored_task.progress = 100
                stored_task.result = json.dumps(
                    {"outcome": "extracted", "frames": len(files), "generation": generation}
                )
                stored_task.error = None
                stored_task.finished_at = now
                stored_task.updated_at = now
                stored_task.lease_owner = None
                stored_task.lease_expires_at = None
                database.commit()
        except Exception:
            if target.exists():
                shutil.rmtree(target)
            if backup.exists():
                os.replace(backup, target)
            raise
        if backup.exists():
            shutil.rmtree(backup)

    def _load_task(self, task_id: str) -> tuple[Task, Video, dict[str, Any]]:
        with self._session_factory() as database:
            task = database.get(Task, task_id)
            if task is None or task.status != "running" or task.video_id is None:
                raise MediaToolError("active task not found")
            video = database.get(Video, task.video_id)
            if video is None:
                raise MediaToolError("task video not found")
            database.expunge(task)
            database.expunge(video)
            return task, video, json.loads(task.payload)

    def _local_duplicate(self, video: Video, digest: str) -> bool:
        with self._session_factory() as database:
            return (
                database.scalar(
                    select(Video.id).where(
                        Video.project_id == video.project_id,
                        Video.content_sha256 == digest,
                        Video.id != video.id,
                    )
                )
                is not None
            )

    def _remote_duplicate(self, video: Video, extractor: str, external_id: str) -> bool:
        with self._session_factory() as database:
            return (
                database.scalar(
                    select(Video.id).where(
                        Video.project_id == video.project_id,
                        Video.extractor == extractor,
                        Video.external_id == external_id,
                        Video.id != video.id,
                    )
                )
                is not None
            )

    def _make_thumbnail(self, video: Path, target: Path) -> Path | None:
        try:
            result = self._run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-ss",
                    "0",
                    "-i",
                    str(video),
                    "-frames:v",
                    "1",
                    "-vf",
                    "scale=320:-2",
                    "-y",
                    str(target),
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return target if result.returncode == 0 and target.is_file() else None
        except (OSError, subprocess.TimeoutExpired):
            return None

    def _publish(
        self,
        task: Task,
        video: Video,
        source: Path,
        metadata: MediaMetadata,
        *,
        thumbnail: Path | None,
        content_sha256: str | None = None,
    ) -> None:
        videos_dir = self.workspace / "projects" / video.project_id / "videos"
        thumbnails_dir = self.workspace / "projects" / video.project_id / "thumbnails"
        videos_dir.mkdir(parents=True, exist_ok=True)
        destination = videos_dir / f"{video.short_code}{source.suffix.lower()}"
        os.replace(source, destination)
        thumbnail_destination = None
        if thumbnail is not None and thumbnail.is_file():
            thumbnails_dir.mkdir(parents=True, exist_ok=True)
            thumbnail_destination = thumbnails_dir / f"{video.short_code}_thumbnail.jpg"
            os.replace(thumbnail, thumbnail_destination)

        now = self._now()
        try:
            with self._session_factory() as database:
                stored_video = database.get(Video, video.id)
                stored_task = database.get(Task, task.id)
                if stored_video is None or stored_task is None:
                    raise MediaToolError("task resources disappeared")
                stored_video.title = video.title
                stored_video.source_url = video.source_url
                stored_video.extractor = video.extractor
                stored_video.external_id = video.external_id
                stored_video.content_sha256 = content_sha256
                stored_video.file_path = destination.relative_to(self.workspace).as_posix()
                stored_video.thumbnail_path = (
                    thumbnail_destination.relative_to(self.workspace).as_posix()
                    if thumbnail_destination
                    else None
                )
                stored_video.duration = metadata.duration
                stored_video.width = metadata.width
                stored_video.height = metadata.height
                stored_video.fps = metadata.fps
                stored_video.total_frames = metadata.total_frames
                stored_video.file_size = metadata.file_size
                stored_video.status = "ready"
                stored_video.version += 1
                stored_video.updated_at = now
                stored_task.status = "succeeded"
                stored_task.progress = 100
                stored_task.result = json.dumps({"outcome": "imported"})
                stored_task.error = None
                stored_task.finished_at = now
                stored_task.updated_at = now
                stored_task.lease_owner = None
                stored_task.lease_expires_at = None
                database.commit()
        except Exception:
            destination.unlink(missing_ok=True)
            if thumbnail_destination:
                thumbnail_destination.unlink(missing_ok=True)
            raise

    def _heartbeat(self, task_id: str, progress: int | None) -> None:
        with self._session_factory() as database:
            task = database.get(Task, task_id)
            if task is None or task.status != "running":
                return
            now = self._now()
            if progress is not None:
                task.progress = max(task.progress, progress)
            task.updated_at = now
            task.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
            database.commit()

    def _cancel_requested(self, task_id: str) -> bool:
        with self._session_factory() as database:
            task = database.get(Task, task_id)
            return task is None or task.cancel_requested or task.status != "running"

    def _finish_duplicate(self, task_id: str, reason: str) -> None:
        now = self._now()
        with self._session_factory() as database:
            task = database.get(Task, task_id)
            if task is None:
                return
            video = database.get(Video, task.video_id) if task.video_id else None
            task.video_id = None
            task.status = "succeeded"
            task.progress = 100
            task.result = json.dumps({"outcome": "skipped", "reason": reason})
            task.finished_at = now
            task.updated_at = now
            task.lease_owner = None
            task.lease_expires_at = None
            if video is not None:
                database.delete(video)
            database.commit()

    def _finish_canceled(self, task_id: str) -> None:
        now = self._now()
        with self._session_factory() as database:
            task = database.get(Task, task_id)
            if task is None:
                return
            task.status = "canceled"
            task.finished_at = now
            task.updated_at = now
            task.lease_owner = None
            task.lease_expires_at = None
            self._fail_imported_model(database, task, "model import canceled")
            self._finish_dataset_export(database, task, "canceled", "dataset export canceled")
            database.commit()

    def _safe_error(self, exc: Exception) -> str:
        value = str(exc).replace(str(self.settings.home), "~")
        value = value.replace(str(self.workspace), ".vision-dataset-workbench")
        return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", value).strip()[:2000]

    def _finish_failed(self, task_id: str, exc: Exception) -> None:
        now = self._now()
        with self._session_factory() as database:
            task = database.get(Task, task_id)
            if task is None:
                return
            task.status = "failed"
            task.error = self._safe_error(exc) or "task failed"
            task.finished_at = now
            task.updated_at = now
            task.lease_owner = None
            task.lease_expires_at = None
            self._fail_imported_model(database, task, task.error)
            self._finish_dataset_export(database, task, "failed", task.error)
            database.commit()

    @staticmethod
    def _fail_imported_model(database, task: Task, error: str) -> None:
        if task.type != "import_model":
            return
        model_id = str(json.loads(task.payload).get("model_id") or "")
        model = database.get(InferenceModel, model_id)
        if model is not None:
            model.status = "failed"
            model.error = error
            model.updated_at = task.updated_at

    @staticmethod
    def _finish_dataset_export(
        database, task: Task, status: str, error: str
    ) -> None:
        if task.type != "export_dataset":
            return
        export_id = str(json.loads(task.payload).get("export_id") or "")
        record = database.get(DatasetExport, export_id)
        if record is not None:
            record.status = status
            record.error = error
            record.completed_at = task.updated_at

    def _remove_task_temp(self, path: Path) -> None:
        expected_parent = (self.workspace / "tmp").resolve()
        if path.parent.resolve() != expected_parent:
            raise RuntimeError("unsafe task temp path")
        if path.exists():
            shutil.rmtree(path)

    def run_once(self) -> None:
        for task_id, future in list(self._futures.items()):
            if future.done():
                future.result()
                del self._futures[task_id]
        for task in self.claim_available():
            self._futures[task.id] = self._executor.submit(self.execute_task, task.id)

    def run(self, poll_interval: float = 0.5) -> None:
        while not self._stop.is_set():
            self.run_once()
            self._stop.wait(poll_interval)
        self._executor.shutdown(wait=True, cancel_futures=False)

    def stop(self) -> None:
        self._stop.set()


def _workspace(settings: RuntimeSettings) -> Path:
    locator = WorkspaceLocator(default_locator_path(settings.home))
    workspace = settings.workspace or locator.read()
    if (
        workspace is None
        or not workspace.is_relative_to(settings.home)
        or not (workspace / "db" / "workbench.sqlite3").is_file()
    ):
        raise SystemExit("Vision Dataset Workbench is not initialized")
    return workspace


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Vision Dataset Workbench task worker")
    parser.add_argument("--once", action="store_true", help="claim and execute available tasks once")
    parser.add_argument("--poll-interval", type=float, default=0.5)
    args = parser.parse_args()
    settings = RuntimeSettings.from_env()
    workspace = _workspace(settings)
    engine = make_engine(workspace / "db" / "workbench.sqlite3")
    worker = TaskWorker(engine, settings, workspace)
    if args.once:
        claimed = worker.claim_available()
        for task in claimed:
            worker.execute_task(task.id)
        engine.dispose()
        return

    # ponytail: one scheduler per workspace; add distributed claims only if
    # cross-host workers become a requirement.
    signal.signal(signal.SIGINT, lambda *_: worker.stop())
    signal.signal(signal.SIGTERM, lambda *_: worker.stop())
    try:
        worker.run(args.poll_interval)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
