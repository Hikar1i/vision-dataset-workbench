import pytest

from vision_dataset_workbench.storage.paths import HomePathResolver, UnsafePathError


def test_resolves_home_relative_directory(tmp_path):
    target = tmp_path / "datasets"
    target.mkdir()
    resolver = HomePathResolver(tmp_path)

    assert resolver.resolve_existing("datasets") == target.resolve()
    assert resolver.display(target) == "~/datasets"


def test_rejects_parent_escape(tmp_path):
    resolver = HomePathResolver(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()

    with pytest.raises(UnsafePathError):
        resolver.resolve_existing(f"../{outside.name}")


def test_rejects_symlink_escape(tmp_path):
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    (tmp_path / "link").symlink_to(outside, target_is_directory=True)

    with pytest.raises(UnsafePathError):
        HomePathResolver(tmp_path).resolve_existing("link")
