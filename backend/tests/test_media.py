import json
import subprocess
from pathlib import Path

import pytest

from vision_dataset_workbench.config import RuntimeSettings
from vision_dataset_workbench.media import (
    InvalidMediaSource,
    MediaToolError,
    normalize_remote_url,
    preview_remote,
    probe_video,
    ytdlp_base_args,
)


def settings(tmp_path, **values):
    return RuntimeSettings(home=tmp_path, workspace=None, **values)


def completed(stdout="", stderr="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_remote_urls_and_instance_yt_dlp_options(tmp_path):
    assert normalize_remote_url(" `https://example.test/video?id=1` ") == (
        "https://example.test/video?id=1"
    )
    for invalid in ("", "file:///etc/passwd", "ftp://example.test/video", "echo test"):
        with pytest.raises(InvalidMediaSource):
            normalize_remote_url(invalid)

    args = ytdlp_base_args(
        settings(
            tmp_path,
            ytdlp_proxy="http://127.0.0.1:7890",
            ytdlp_cookie_file=Path("/run/secrets/cookies.txt"),
        )
    )
    assert args[-4:] == [
        "--proxy",
        "http://127.0.0.1:7890",
        "--cookies",
        "/run/secrets/cookies.txt",
    ]
    assert "--no-check-certificates" not in args
    assert "--cookies-from-browser" not in args


def test_remote_preview_parses_single_and_playlist(tmp_path):
    calls = []

    def single_run(command, **kwargs):
        calls.append((command, kwargs))
        return completed(
            json.dumps(
                {
                    "id": "abc",
                    "extractor_key": "Generic",
                    "title": "Single",
                    "webpage_url": "https://example.test/single",
                    "duration": 12.5,
                }
            )
        )

    single = preview_remote("https://example.test/single", settings(tmp_path), run=single_run)
    assert single[0].external_id == "abc"
    assert single[0].url == "https://example.test/single"
    assert "--playlist-end" in calls[0][0]
    assert calls[0][1]["timeout"] == 60

    def playlist_run(_command, **_kwargs):
        return completed(
            json.dumps(
                {
                    "title": "Playlist",
                    "entries": [
                        {
                            "id": "one",
                            "extractor": "youtube",
                            "title": "One",
                            "url": "https://example.test/one",
                            "duration": 3,
                            "playlist_index": 7,
                        }
                    ],
                }
            )
        )

    playlist = preview_remote(
        "https://example.test/list", settings(tmp_path), run=playlist_run
    )
    assert [(item.title, item.playlist, item.playlist_index) for item in playlist] == [
        ("One", "Playlist", 7)
    ]


def test_remote_preview_cleans_tool_errors(tmp_path):
    def failed(_command, **_kwargs):
        return completed(stderr="\x1b[31mnetwork failed\x1b[0m", returncode=1)

    with pytest.raises(MediaToolError, match="network failed") as raised:
        preview_remote("https://example.test/video", settings(tmp_path), run=failed)
    assert "\x1b" not in str(raised.value)


def test_ffprobe_metadata_uses_fraction_fps(tmp_path):
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"12345")

    def fake_run(command, **kwargs):
        assert command[0] == "ffprobe"
        assert kwargs["timeout"] == 30
        return completed(
            json.dumps(
                {
                    "format": {"duration": "10.0"},
                    "streams": [
                        {
                            "codec_type": "video",
                            "width": 1920,
                            "height": 1080,
                            "avg_frame_rate": "30000/1001",
                        }
                    ],
                }
            )
        )

    metadata = probe_video(video, run=fake_run)
    assert metadata.width == 1920
    assert metadata.height == 1080
    assert metadata.fps == pytest.approx(29.97003)
    assert metadata.total_frames == 300
    assert metadata.file_size == 5
