# Proofline desktop shell

This Tauri v2 shell starts a bundled Proofline Python sidecar on a random
loopback port, waits for a structured readiness event, and then navigates the
native webview to the local application. Persistent state is owned by the
operating-system application data directory. Provider credentials continue to
use the operating-system keyring.

Build on the target operating system; PyInstaller binaries are not
cross-platform. From the repository root:

```bash
make desktop-check
make desktop-build
```

The first command creates the target-triple-named sidecar and compiles a debug
shell without producing an installer. The second produces the installers
supported by the current platform. macOS distribution still requires Apple
signing/notarization; Windows distribution still requires a real Windows build
and qualification receipt.
