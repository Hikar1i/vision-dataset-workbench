from pathlib import Path
from runpy import run_path

import pytest

rewrite = run_path(str(Path(__file__).resolve().parents[2] / "deploy/apt_mirror.py"))["rewrite_sources"]
SOURCE = """URIs: http://deb.debian.org/debian
Suites: bookworm bookworm-updates
Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg
URIs: https://security.debian.org/debian-security
Suites: bookworm-security
"""


def test_mirror_keeps_suites_keys_and_default():
    assert rewrite(SOURCE, "") == SOURCE
    result = rewrite(SOURCE, "https://mirror.example/")
    assert "https://mirror.example/debian\n" in result
    assert "https://mirror.example/debian-security\n" in result
    assert "Suites: bookworm-security" in result
    assert "Signed-By: /usr/share/keyrings/debian-archive-keyring.gpg" in result


@pytest.mark.parametrize("mirror", ["file:///tmp", "https://user:secret@example.com", "https://example.com/debian", "https://example.com?key=secret", "https://bad host", "https://example.com:bad"])
def test_mirror_rejects_unsafe_or_ambiguous_origins(mirror):
    with pytest.raises(ValueError, match="VDW_DEBIAN_MIRROR"):
        rewrite(SOURCE, mirror)
