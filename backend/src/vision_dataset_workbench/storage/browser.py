from pathlib import Path

from .paths import HomePathResolver, UnsafePathError

VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".flv",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".ogv",
    ".webm",
    ".wmv",
}
MODEL_EXTENSIONS = {".pt", ".onnx"}


def list_home_entries(
    resolver: HomePathResolver,
    relative: str,
    *,
    page: int,
    page_size: int,
    hidden_root: Path | None = None,
    include_video_files: bool = False,
    include_model_files: bool = False,
) -> dict[str, object]:
    directory = resolver.resolve_existing(relative)
    hidden = hidden_root.resolve() if hidden_root is not None else None
    if hidden is not None and (directory == hidden or directory.is_relative_to(hidden)):
        raise UnsafePathError("managed workspace is not browsable")

    children: list[tuple[Path, str]] = []
    for item in directory.iterdir():
        if item.name.startswith("."):
            continue
        try:
            resolved = item.resolve(strict=True)
        except OSError:
            continue
        if not resolved.is_relative_to(resolver.home):
            continue
        if hidden is not None and (resolved == hidden or resolved.is_relative_to(hidden)):
            continue
        if item.is_dir():
            children.append((item, "directory"))
        elif include_video_files and item.is_file() and item.suffix.lower() in VIDEO_EXTENSIONS:
            children.append((item, "file"))
        elif include_model_files and item.is_file() and item.suffix.lower() in MODEL_EXTENSIONS:
            children.append((item, "file"))

    children.sort(key=lambda entry: (entry[1] == "file", entry[0].name.casefold()))
    start = (page - 1) * page_size
    items = [
        {
            "name": item.name,
            "path": item.relative_to(resolver.home).as_posix(),
            "type": item_type,
            "size": item.stat().st_size if item_type == "file" else None,
        }
        for item, item_type in children[start : start + page_size]
    ]
    parent = (
        None
        if directory == resolver.home
        else directory.parent.relative_to(resolver.home).as_posix()
    )
    return {
        "path": resolver.display(directory),
        "parent": parent,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": len(children),
    }


def create_home_directory(
    resolver: HomePathResolver, parent: str, name: str
) -> dict[str, str]:
    target = resolver.resolve_child(parent, name)
    target.mkdir()
    return {
        "path": target.relative_to(resolver.home).as_posix(),
        "display_path": resolver.display(target),
    }
