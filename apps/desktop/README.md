# Desktop shell

The Tauri v2 shell starts a target-specific frozen Python sidecar, waits for loopback readiness,
and opens the bundled Proofline UI in a native webview. State uses the operating-system application
data directory and provider secrets use the OS keyring.

From the repository root:

```bash
make desktop-check
make desktop-build
```

PyInstaller sidecars are not cross-platform. Build and qualify on the target OS. Current macOS
packages are experimental and unsigned; Windows requires the workflow in
[`docs/windows-release.md`](../../docs/windows-release.md). Signing, notarization, uninstall,
upgrade, and updater rollback remain open gates.
