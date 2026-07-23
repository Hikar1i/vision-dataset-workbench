import json
import re
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .config import RuntimeSettings


class InvalidMediaSource(ValueError):
    pass


class MediaToolError(RuntimeError):
    pass


@dataclass(frozen=True)
class RemotePreview:
    title: str
    url: str
    duration: float
    extractor: str
    external_id: str
    playlist: str = ""
    playlist_index: int | None = None


@dataclass(frozen=True)
class MediaMetadata:
    duration: float
    width: int
    height: int
    fps: float
    total_frames: int
    file_size: int


CommandRunner = Callable[..., subprocess.CompletedProcess[str]]


def _clean_error(value: str) -> str:
    return re.sub(r"\x1B\[[0-?]*[ -/]*[@-~]", "", value).strip()[:2000]


def normalize_remote_url(raw: str) -> str:
    value = str(raw or "").strip()
    while len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
        value = value[1:-1].strip()
    value = value.strip(" \t\r\n\"'`")
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise InvalidMediaSource("remote URL must use http or https")
    return value


def ytdlp_base_args(settings: RuntimeSettings) -> list[str]:
    args = [sys.executable, "-m", "yt_dlp"]
    if settings.ytdlp_proxy:
        args.extend(["--proxy", settings.ytdlp_proxy])
    if settings.ytdlp_cookie_file:
        args.extend(["--cookies", str(settings.ytdlp_cookie_file)])
    return args


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0


def _preview_item(
    info: dict[str, Any], input_url: str, *, playlist: str = "", index: int | None = None
) -> RemotePreview:
    url = normalize_remote_url(
        info.get("webpage_url")
        or info.get("original_url")
        or info.get("url")
        or input_url
    )
    external_id = str(info.get("id") or "").strip()
    extractor = str(info.get("extractor_key") or info.get("extractor") or "generic").strip()
    if not external_id:
        raise MediaToolError("yt-dlp returned an item without an id")
    return RemotePreview(
        title=str(info.get("title") or external_id),
        url=url,
        duration=_number(info.get("duration")),
        extractor=extractor,
        external_id=external_id,
        playlist=playlist,
        playlist_index=info.get("playlist_index") or index,
    )


def preview_remote(
    raw_url: str,
    settings: RuntimeSettings,
    *,
    run: CommandRunner = subprocess.run,
) -> list[RemotePreview]:
    url = normalize_remote_url(raw_url)
    command = [
        *ytdlp_base_args(settings),
        "--dump-single-json",
        "--flat-playlist",
        "--playlist-end",
        "999",
        "--no-warnings",
        "--",
        url,
    ]
    try:
        result = run(command, capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaToolError(_clean_error(str(exc)) or "yt-dlp preview failed") from exc
    if result.returncode != 0:
        raise MediaToolError(_clean_error(result.stderr) or "yt-dlp preview failed")
    try:
        info = json.loads(result.stdout)
        entries = info.get("entries")
        if entries is None:
            return [_preview_item(info, url)]
        playlist = str(info.get("title") or "")
        return [
            _preview_item(entry, url, playlist=playlist, index=index)
            for index, entry in enumerate(entries[:999], start=1)
            if entry
        ]
    except (InvalidMediaSource, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise MediaToolError("yt-dlp returned invalid metadata") from exc


def _fps(stream: dict[str, Any]) -> float:
    raw = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    try:
        return float(Fraction(str(raw)))
    except (ValueError, ZeroDivisionError):
        return 0


def probe_video(
    path: Path, *, run: CommandRunner = subprocess.run
) -> MediaMetadata:
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    try:
        result = run(command, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise MediaToolError(_clean_error(str(exc)) or "ffprobe failed") from exc
    if result.returncode != 0:
        raise MediaToolError(_clean_error(result.stderr) or "ffprobe failed")
    try:
        data = json.loads(result.stdout)
        stream = next(
            item for item in data.get("streams", []) if item.get("codec_type") == "video"
        )
        duration = _number(data.get("format", {}).get("duration") or stream.get("duration"))
        fps = _fps(stream)
        frames = int(stream.get("nb_frames") or 0)
        if frames <= 0 and duration > 0 and fps > 0:
            frames = round(duration * fps)
        return MediaMetadata(
            duration=duration,
            width=int(stream.get("width") or 0),
            height=int(stream.get("height") or 0),
            fps=fps,
            total_frames=frames,
            file_size=path.stat().st_size,
        )
    except (StopIteration, TypeError, ValueError, json.JSONDecodeError, OSError) as exc:
        raise MediaToolError("ffprobe returned invalid video metadata") from exc
