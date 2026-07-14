# Real-Windows qualification and local release

Windows support is not inferred from cross-compilation or a macOS build. Run this workflow from a
real Windows x64 machine with Python 3.12, Node.js, Rust/MSVC, WebView2, WiX/NSIS prerequisites and
GitHub CLI authentication:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\pip.exe install -e ".[dev]"
npm install
powershell -ExecutionPolicy Bypass -File scripts\release_windows.ps1 -Tag v0.14.17
```

The script requires clean `main == origin/main` and a `[skip ci]` release commit. It runs the full
credential-free test/evaluation gate, builds the wheel, frozen sidecar, MSI and NSIS installers,
qualifies the installed wheel and Windows Credential Locker, writes checksummed Windows receipts,
then creates the tag/release directly through `gh`. It does not invoke GitHub Actions.

The Windows desktop receipt proves only the target-specific build and frozen-sidecar lifecycle.
Installer UI, uninstall, upgrade/rollback and Authenticode signing remain explicit manual gates and
must not be marked complete from this receipt alone.
