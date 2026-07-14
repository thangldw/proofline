import runpy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sidecar_destination = runpy.run_path(ROOT / "scripts/build_desktop_sidecar.py")[
    "sidecar_destination"
]


def test_sidecar_destination_uses_tauri_target_triple_name():
    mac = sidecar_destination("aarch64-apple-darwin")
    windows = sidecar_destination("x86_64-pc-windows-msvc")

    assert mac.name == "proofline-sidecar-aarch64-apple-darwin"
    assert windows.name == "proofline-sidecar-x86_64-pc-windows-msvc.exe"
    assert mac.parent == ROOT / "apps/desktop/src-tauri/binaries"
