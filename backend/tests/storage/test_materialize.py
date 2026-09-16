import errno
import os

from vision_dataset_workbench.storage import materialize


def test_materialize_falls_back_from_reflink_to_hardlink(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    target = tmp_path / "target.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(
        materialize.fcntl,
        "ioctl",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EOPNOTSUPP, "unsupported")),
    )

    method = materialize.materialize_immutable_file(source, target)

    assert method == "hardlink"
    assert target.read_bytes() == b"video"
    assert os.stat(source).st_ino == os.stat(target).st_ino


def test_materialize_falls_back_to_copy(tmp_path, monkeypatch):
    source = tmp_path / "source.mp4"
    target = tmp_path / "target.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr(
        materialize.fcntl,
        "ioctl",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EOPNOTSUPP, "unsupported")),
    )
    monkeypatch.setattr(
        materialize.os,
        "link",
        lambda *_args: (_ for _ in ()).throw(OSError(errno.EXDEV, "cross-device")),
    )

    method = materialize.materialize_immutable_file(source, target)

    assert method == "copy"
    assert target.read_bytes() == b"video"
    assert os.stat(source).st_ino != os.stat(target).st_ino
