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

from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker

from .config import RuntimeSettings
from .database import make_engine
from .media import MediaMetadata, MediaToolError, normalize_remote_url, probe_video, ytdlp_base_args
from .models import Task, Video
from .storage.browser import VIDEO_EXTENSIONS
from .storage.locator import WorkspaceLocator, default_locator_path
from .storage.paths import HomePathResolver, UnsafePathError

LIMITS = {"copy_video": 2, "download_video": 2}
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
    ):
        self.engine = engine
        self.settings = settings
        self.workspace = workspace.resolve()
        self._probe = probe
        self._popen = popen
        self._run = run
        self._now = now
        self.worker_id = worker_id or str(uuid4())
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
            else:
                raise RuntimeError("unsupported task type")
        except TaskCanceled:
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
        destination = videos_dir / f"{video.id}{source.suffix.lower()}"
        os.replace(source, destination)
        thumbnail_destination = None
        if thumbnail is not None and thumbnail.is_file():
            thumbnails_dir.mkdir(parents=True, exist_ok=True)
            thumbnail_destination = thumbnails_dir / f"{video.id}.jpg"
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
            database.commit()

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
