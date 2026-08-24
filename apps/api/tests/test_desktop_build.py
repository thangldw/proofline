import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
DESKTOP_WORKFLOW = ROOT / ".github/workflows/desktop-artifacts.yml"
sidecar_destination = runpy.run_path(SCRIPTS / "build_desktop_sidecar.py")["sidecar_destination"]
macos_release_qualification = runpy.run_path(SCRIPTS / "desktop_release_receipt.py")[
    "macos_release_qualification"
]
sys.path.insert(0, str(SCRIPTS))
try:
    windows_receipt_namespace = runpy.run_path(SCRIPTS / "windows_desktop_receipt.py")
    windows_release_qualification = windows_receipt_namespace["windows_release_qualification"]
    authenticode_status = windows_receipt_namespace["authenticode_status"]
finally:
    sys.path.remove(str(SCRIPTS))


def test_sidecar_destination_uses_tauri_target_triple_name():
    mac = sidecar_destination("aarch64-apple-darwin")
    windows = sidecar_destination("x86_64-pc-windows-msvc")

    assert mac.name == "proofline-sidecar-aarch64-apple-darwin"
    assert windows.name == "proofline-sidecar-x86_64-pc-windows-msvc.exe"
    assert mac.parent == ROOT / "apps/desktop/src-tauri/binaries"


def test_desktop_workflow_is_compatible_with_macos_system_bash():
    workflow = DESKTOP_WORKFLOW.read_text(encoding="utf-8")

    assert "${RELEASE_GRADE,,}" not in workflow


def test_experimental_macos_build_does_not_export_notarization_credentials():
    workflow = DESKTOP_WORKFLOW.read_text(encoding="utf-8")
    experimental = workflow.split("- name: Build experimental macOS package", maxsplit=1)[1]
    experimental = experimental.split("- name: Build release-grade macOS package", maxsplit=1)[0]

    assert "APPLE_SIGNING_IDENTITY" in experimental
    assert "APPLE_ID" not in experimental
    assert "APPLE_PASSWORD" not in experimental
    assert "APPLE_TEAM_ID" not in experimental


def test_macos_release_qualification_requires_developer_id_and_native_checks():
    assert (
        macos_release_qualification(
            release_grade=True,
            signature_kind="developer_id_or_other",
            codesign_valid=True,
            gatekeeper_valid=True,
            stapled_app=True,
            stapled_dmg=True,
        )
        == "release_grade_macos_signed_notarized"
    )
    with pytest.raises(RuntimeError, match="macos_release_qualification_failed"):
        macos_release_qualification(
            release_grade=True,
            signature_kind="adhoc",
            codesign_valid=True,
            gatekeeper_valid=True,
            stapled_app=True,
            stapled_dmg=True,
        )


def test_windows_release_qualification_requires_valid_authenticode_everywhere():
    assert (
        windows_release_qualification(release_grade=True, statuses=["Valid", "Valid"])
        == "release_grade_windows_authenticode_signed"
    )
    with pytest.raises(RuntimeError, match="windows_release_qualification_failed"):
        windows_release_qualification(release_grade=True, statuses=["Valid", "NotSigned"])


def test_authenticode_probe_prefers_runner_powershell(monkeypatch, tmp_path):
    invocations = []

    monkeypatch.setattr(
        windows_receipt_namespace["shutil"],
        "which",
        lambda candidate: (
            "C:/Program Files/PowerShell/7/pwsh.exe"
            if candidate == "pwsh"
            else "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe"
        ),
    )

    def fake_run(command, **kwargs):
        invocations.append((command, kwargs))
        return SimpleNamespace(returncode=0, stdout="NotSigned\n", stderr="")

    monkeypatch.setattr(windows_receipt_namespace["subprocess"], "run", fake_run)

    assert authenticode_status(tmp_path / "proofline.exe") == "NotSigned"
    assert invocations[0][0][0].endswith("pwsh.exe")
