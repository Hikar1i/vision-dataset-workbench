from pathlib import Path


class UnsafePathError(ValueError):
    pass


class HomePathResolver:
    def __init__(self, home: Path):
        self.home = home.resolve()

    def _assert_inside_home(self, path: Path) -> Path:
        try:
            path.relative_to(self.home)
        except ValueError as exc:
            raise UnsafePathError("path escapes the service user's home") from exc
        return path

    def resolve_existing(self, relative: str) -> Path:
        if Path(relative).is_absolute():
            raise UnsafePathError("absolute paths are not accepted")
        return self._assert_inside_home((self.home / relative).resolve(strict=True))

    def resolve_child(self, parent_relative: str, name: str) -> Path:
        if (
            not name
            or name in {".", ".."}
            or "/" in name
            or "\\" in name
            or Path(name).name != name
        ):
            raise UnsafePathError("invalid directory name")
        parent = self.resolve_existing(parent_relative)
        return self._assert_inside_home((parent / name).resolve(strict=False))

    def display(self, path: Path) -> str:
        relative = self._assert_inside_home(path.resolve()).relative_to(self.home)
        return "~" if not relative.parts else f"~/{relative.as_posix()}"
