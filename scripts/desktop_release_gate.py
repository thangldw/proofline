#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections.abc import Mapping

REQUIRED_CREDENTIALS = {
    "macos": (
        "apple_certificate",
        "apple_certificate_password",
        "keychain_password",
        "apple_signing_identity",
        "apple_id",
        "apple_password",
        "apple_team_id",
    ),
    "windows": (
        "windows_certificate",
        "windows_certificate_password",
        "windows_certificate_thumbprint",
        "windows_timestamp_url",
    ),
}


class DesktopReleaseGateError(ValueError):
    def __init__(self, code: str, *, missing: tuple[str, ...] = ()) -> None:
        self.code = code
        self.missing = missing
        super().__init__(code)


def evaluate_desktop_release(
    platform: str, *, release_grade: bool, credentials: Mapping[str, bool]
) -> dict[str, object]:
    if platform not in REQUIRED_CREDENTIALS:
        raise DesktopReleaseGateError("desktop_release_platform_invalid")
    unexpected = set(credentials) - set(REQUIRED_CREDENTIALS[platform])
    if unexpected or any(value not in (True, False) for value in credentials.values()):
        raise DesktopReleaseGateError("desktop_release_credential_invalid")
    if not release_grade:
        return {
            "schema_version": "proofline.desktop-release-gate.v1",
            "platform": platform,
            "release_grade": False,
            "approved": True,
            "qualification": f"experimental_{platform}_unsigned_not_for_distribution",
            "required_credentials": [],
        }

    required = REQUIRED_CREDENTIALS[platform]
    missing = tuple(name for name in required if credentials.get(name) is not True)
    if missing:
        raise DesktopReleaseGateError(
            f"desktop_release_credentials_missing_{platform}", missing=missing
        )
    return {
        "schema_version": "proofline.desktop-release-gate.v1",
        "platform": platform,
        "release_grade": True,
        "approved": True,
        "qualification": "release_grade_credentials_present_unverified",
        "required_credentials": list(required),
    }


def _credential_flags(values: list[str]) -> dict[str, bool]:
    credentials: dict[str, bool] = {}
    for value in values:
        try:
            name, present = value.split("=", 1)
        except ValueError as exc:
            raise DesktopReleaseGateError("desktop_release_credential_invalid") from exc
        if name in credentials or present not in {"true", "false"}:
            raise DesktopReleaseGateError("desktop_release_credential_invalid")
        credentials[name] = present == "true"
    return credentials


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Approve an experimental desktop build or fail closed on credential presence."
    )
    parser.add_argument("--platform", required=True, choices=tuple(REQUIRED_CREDENTIALS))
    parser.add_argument("--release-grade", action="store_true")
    parser.add_argument("--credential", action="append", default=[])
    args = parser.parse_args()
    try:
        report = evaluate_desktop_release(
            args.platform,
            release_grade=args.release_grade,
            credentials=_credential_flags(args.credential),
        )
    except DesktopReleaseGateError as exc:
        raise SystemExit(f"desktop release gate failed: {exc.code}") from exc
    print(json.dumps(report, sort_keys=True))


if __name__ == "__main__":
    main()
