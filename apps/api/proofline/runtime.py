from __future__ import annotations

import argparse
import os
from pathlib import Path


def _bootstrap_data_dir(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("command", nargs="?")
    parser.add_argument("--data-dir", type=Path)
    args, _ = parser.parse_known_args(argv)
    if args.command != "serve" or args.data_dir is None:
        return
    data_dir = args.data_dir.expanduser().resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    if not data_dir.is_dir():
        raise SystemExit("serve failed: data_dir_not_directory")
    os.environ["PROOFLINE_HOME"] = str(data_dir)


def main(argv: list[str] | None = None) -> None:
    import sys

    arguments = list(sys.argv[1:] if argv is None else argv)
    _bootstrap_data_dir(arguments)

    from .cli import main as cli_main

    cli_main(arguments)


if __name__ == "__main__":
    main()
