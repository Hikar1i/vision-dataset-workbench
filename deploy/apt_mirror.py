"""Configure the Debian base-image repositories without changing suites or keys."""
import os
from pathlib import Path
from urllib.parse import urlsplit


def rewrite_sources(text: str, mirror: str) -> str:
    if not mirror:
        return text
    try:
        url = urlsplit(mirror)
        valid = (
            url.scheme in {"http", "https"}
            and url.hostname
            and url.username is None
            and url.password is None
            and url.path in {"", "/"}
            and not url.query
            and not url.fragment
            and "?" not in mirror
            and "#" not in mirror
            and not any(character.isspace() for character in mirror)
        )
        url.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("VDW_DEBIAN_MIRROR must be an HTTP(S) origin without credentials or a repository path")
    for host in ("deb.debian.org", "security.debian.org"):
        for scheme in ("http", "https"):
            text = text.replace(f"{scheme}://{host}/", mirror.rstrip("/") + "/")
    return text


if __name__ == "__main__":
    mirror = os.environ.get("VDW_DEBIAN_MIRROR", "")
    if mirror:
        source = Path("/etc/apt/sources.list.d/debian.sources")
        source.write_text(rewrite_sources(source.read_text(), mirror))
