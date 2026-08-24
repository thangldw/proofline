#!/usr/bin/env python3
"""Select only explicitly qualified non-desktop artifacts for a GitHub release."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

from release_check import python_version_for

PLATFORM_SLUG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def select_release_assets(
    dist_dir: Path, *, tag: str, web_format: str, platform_slug: str
) -> list[Path]:
    if not PLATFORM_SLUG.fullmatch(platform_slug):
        raise ValueError(
            "platform slug must contain only letters, digits, dot, underscore, or dash"
        )
    python_version = python_version_for(tag)
    root = dist_dir.resolve(strict=True)
    names = (
        f"proofline_evidence-{python_version}-py3-none-any.whl",
        f"proofline_evidence-{python_version}.tar.gz",
        f"proofline-web-{tag}.{web_format}",
        f"proofline-platform-{tag}-{platform_slug}.json",
    )
    assets = [root / name for name in names]
    missing = [path.name for path in assets if not path.is_file()]
    if missing:
        raise ValueError(f"required release artifacts are missing: {', '.join(missing)}")
    return assets


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dist-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--web-format", choices=("tar.gz", "zip"), required=True)
    parser.add_argument("--platform-slug", required=True)
    args = parser.parse_args()
    try:
        assets = select_release_assets(
            args.dist_dir,
            tag=args.tag,
            web_format=args.web_format,
            platform_slug=args.platform_slug,
        )
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    for asset in assets:
        print(asset)


if __name__ == "__main__":
    main()
