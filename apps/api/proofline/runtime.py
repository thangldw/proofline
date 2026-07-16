from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def default_app_data_dir(
    *,
    platform_name: str | None = None,
    environment: dict[str, str] | None = None,
    home: Path | None = None,
) -> Path:
    platform_name = platform_name or sys.platform
    environment = environment if environment is not None else os.environ
    home = home or Path.home()
    if platform_name == "darwin":
        return home / "Library" / "Application Support" / "Proofline"
    if platform_name == "win32":
        local_app_data = environment.get("LOCALAPPDATA")
        if not local_app_data:
            raise ValueError("LOCALAPPDATA is unavailable")
        return Path(local_app_data) / "Proofline"
    xdg_data_home = environment.get("XDG_DATA_HOME")
    return (Path(xdg_data_home) if xdg_data_home else home / ".local" / "share") / "proofline"


def _bootstrap_data_dir(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command", nargs="?")
    parser.add_argument("--data-dir", type=Path)
    args, _ = parser.parse_known_args(argv)
    if args.command not in {"serve", "launch"}:
        return
    if args.data_dir is None:
        if args.command == "serve":
            return
        try:
            data_dir = default_app_data_dir()
        except ValueError as exc:
            raise SystemExit("launch failed: app_data_directory_unavailable") from exc
    else:
        data_dir = args.data_dir
    data_dir = data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    if not data_dir.is_dir():
        raise SystemExit(f"{args.command} failed: data_dir_not_directory")
    os.environ["PROOFLINE_HOME"] = str(data_dir)
    if args.command == "launch" and sys.platform in {"darwin", "win32"}:
        os.environ.setdefault("PROOFLINE_SECRET_STORE", "os_keyring")


def main(argv: list[str] | None = None) -> None:
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments and arguments[0] == "check-decisions":
        os.environ["PROOFLINE_DATABASE_READ_ONLY"] = "true"
    _bootstrap_data_dir(arguments)

    from .cli import main as cli_main

    cli_main(arguments)


if __name__ == "__main__":
    main()
