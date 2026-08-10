from pathlib import Path


def cleanup_intermediate_checkpoints(run_directory: Path) -> list[str]:
    removed: list[str] = []
    weights = (run_directory / "weights").resolve()
    if not weights.is_dir():
        return removed
    for item in weights.iterdir():
        if item.is_file() and item.name.startswith("epoch") and item.suffix == ".pt":
            item.unlink()
            removed.append(item.name)
    return removed
