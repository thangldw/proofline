# ADR 0003: Experimental Tauri packaging

Status: revised and implemented experimentally.

Proofline now packages the bundled web UI and a frozen Python sidecar in Tauri v2. The wrapper uses
dynamic loopback readiness, platform application-data paths, OS keyring mode, and private graceful
shutdown.

```mermaid
flowchart LR
    T["Tauri shell"] --> S["Frozen sidecar"]
    S --> A["Loopback API"]
    A --> U["Bundled UI"]
    S --> D["Platform app data"]
    S --> K["OS keyring"]

    classDef shell fill:#EEE4FF,stroke:#765E9C,color:#172B4D;
    classDef process fill:#DDEBFF,stroke:#5B7DB1,color:#172B4D;
    classDef safe fill:#DDF7EA,stroke:#4C8B6B,color:#172B4D;
    class T shell;
    class S,A,U process;
    class D,K safe;
```

This decision authorizes experimental builds only. Supported native distribution still requires
real-Windows qualification, macOS notarization, Windows Authenticode, install/uninstall/upgrade
receipts, and updater rollback. The Python wheel launcher remains the primary supported experiment.
