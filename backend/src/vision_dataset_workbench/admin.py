import argparse
import getpass
import sys
from collections.abc import Callable, Sequence
from pathlib import Path

from .config import RuntimeSettings
from .services.auth import UserNotFound, build_auth_service, validate_password


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vision-dataset-workbench-admin",
        description="Offline Vision Dataset Workbench administration",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    reset = commands.add_parser("reset-password", help="reset a system administrator password")
    reset.add_argument("--workspace", type=Path, required=True)
    reset.add_argument("--username", required=True)
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    password_reader: Callable[[str], str] = getpass.getpass,
) -> int:
    args = _parser().parse_args(argv)
    workspace = args.workspace.expanduser().resolve()
    if not (workspace / "db" / "workbench.sqlite3").is_file():
        print("error: workspace database does not exist", file=sys.stderr)
        return 1

    first = password_reader("New password: ")
    second = password_reader("Confirm new password: ")
    if first != second:
        print("error: passwords do not match", file=sys.stderr)
        return 1
    try:
        validate_password(first)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    settings = RuntimeSettings(home=workspace.parent, workspace=workspace)
    service = build_auth_service(workspace, settings)
    try:
        service.reset_admin_password(args.username, first)
    except UserNotFound as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    finally:
        service.close()
    print("Administrator password reset successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
