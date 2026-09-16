import fcntl
import os
import shutil
from collections.abc import Callable
from pathlib import Path

FICLONE = 0x40049409


def materialize_immutable_file(
    source: Path,
    target: Path,
    *,
    copy_file: Callable[[Path, Path], None] = shutil.copyfile,
) -> str:
    """Materialize an immutable source without sharing writes when the filesystem permits."""
    if target.exists():
        raise FileExistsError(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source.open("rb") as reader, target.open("xb") as writer:
            fcntl.ioctl(writer.fileno(), FICLONE, reader.fileno())
        return "reflink"
    except OSError:
        target.unlink(missing_ok=True)

    try:
        os.link(source, target)
        return "hardlink"
    except OSError:
        target.unlink(missing_ok=True)

    copy_file(source, target)
    return "copy"
