import runpy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPTS = ROOT / "scripts"
sidecar_destination = runpy.run_path(SCRIPTS / "build_desktop_sidecar.py")["sidecar_destination"]
macos_release_qualification = runpy.run_path(SCRIPTS / "desktop_release_receipt.py")[
    "macos_release_qualification"
]
sys.path.insert(0, str(SCRIPTS))
try:
    windows_release_qualification = runpy.run_path(SCRIPTS / "windows_desktop_receipt.py")[
        "windows_release_qualification"
    ]
finally:
    sys.path.remove(str(SCRIPTS))


def test_sidecar_destination_uses_tauri_target_triple_name():
    mac = sidecar_destination("aarch64-apple-darwin")
    windows = sidecar_destination("x86_64-pc-windows-msvc")

    assert mac.name == "proofline-sidecar-aarch64-apple-darwin"
    assert windows.name == "proofline-sidecar-x86_64-pc-windows-msvc.exe"
    assert mac.parent == ROOT / "apps/desktop/src-tauri/binaries"


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
