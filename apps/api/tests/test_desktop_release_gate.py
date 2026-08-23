import runpy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
namespace = runpy.run_path(ROOT / "scripts/desktop_release_gate.py")
evaluate_desktop_release = namespace["evaluate_desktop_release"]
DesktopReleaseGateError = namespace["DesktopReleaseGateError"]
REQUIRED_CREDENTIALS = namespace["REQUIRED_CREDENTIALS"]


@pytest.mark.parametrize("platform", ["macos", "windows"])
def test_experimental_desktop_build_is_approved_without_credentials(platform):
    report = evaluate_desktop_release(platform, release_grade=False, credentials={})

    assert report == {
        "schema_version": "proofline.desktop-release-gate.v1",
        "platform": platform,
        "release_grade": False,
        "approved": True,
        "qualification": f"experimental_{platform}_unsigned_not_for_distribution",
        "required_credentials": [],
    }


def test_macos_release_grade_fails_closed_without_signing_and_notarization_inputs():
    with pytest.raises(
        DesktopReleaseGateError, match="desktop_release_credentials_missing_macos"
    ) as raised:
        evaluate_desktop_release(
            "macos",
            release_grade=True,
            credentials={"apple_certificate": True, "apple_certificate_password": True},
        )

    assert raised.value.missing == (
        "keychain_password",
        "apple_signing_identity",
        "apple_id",
        "apple_password",
        "apple_team_id",
    )


def test_windows_release_grade_fails_closed_without_authenticode_inputs():
    with pytest.raises(
        DesktopReleaseGateError, match="desktop_release_credentials_missing_windows"
    ) as raised:
        evaluate_desktop_release(
            "windows",
            release_grade=True,
            credentials={"windows_certificate": True},
        )

    assert raised.value.missing == (
        "windows_certificate_password",
        "windows_certificate_thumbprint",
        "windows_timestamp_url",
    )


@pytest.mark.parametrize("platform", ["macos", "windows"])
def test_release_grade_gate_approves_presence_without_claiming_artifact_verification(platform):
    report = evaluate_desktop_release(
        platform,
        release_grade=True,
        credentials={name: True for name in REQUIRED_CREDENTIALS[platform]},
    )

    assert report["approved"] is True
    assert report["qualification"] == "release_grade_credentials_present_unverified"
    assert report["required_credentials"] == list(REQUIRED_CREDENTIALS[platform])


def test_release_gate_rejects_unknown_platform():
    with pytest.raises(DesktopReleaseGateError, match="desktop_release_platform_invalid"):
        evaluate_desktop_release("linux", release_grade=False, credentials={})
