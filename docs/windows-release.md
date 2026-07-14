# Windows local release

Run this only on a real Windows x64 machine with Python 3.12, Node.js, Rust/MSVC, WebView2,
WiX/NSIS prerequisites, and authenticated GitHub CLI.

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip.exe install -e ".[dev]"
npm install
powershell -ExecutionPolicy Bypass -File scripts\release_windows.ps1 -Tag v0.14.17
```

The script requires a clean `main` equal to `origin/main` and a release commit containing
`[skip ci]`. It runs local tests/evaluations, builds wheel, web bundle, frozen sidecar, MSI, and
NSIS, creates installed-wheel and desktop receipts, writes checksums, pushes the tag, and publishes
through GitHub CLI without relying on GitHub Actions.

`windows_desktop_receipt.py` refuses non-Windows hosts. The receipt proves a target-specific build
and sidecar smoke only; it does not prove Authenticode, installer UI, uninstall, upgrade, rollback,
reputation, or production readiness.
