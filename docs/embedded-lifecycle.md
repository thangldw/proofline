# Embedded lifecycle

The bundled launcher and Tauri sidecar share one local runtime contract.

```mermaid
flowchart LR
    U["Launch"] --> D["Resolve app data"]
    D --> M["Apply migrations"]
    M --> S["Start loopback API"]
    S --> R{"Ready?"}
    R -->|yes| W["Open bundled UI"]
    R -->|no| F["Visible startup failure"]
    W --> Q["Graceful shutdown"]
    Q --> C["Remove ready file"]

    classDef start fill:#FFF4C2,stroke:#7A6F45,color:#172B4D;
    classDef action fill:#DDEBFF,stroke:#5B7DB1,color:#172B4D;
    classDef gate fill:#FDE1EF,stroke:#9C5E7B,color:#172B4D;
    classDef success fill:#DDF7EA,stroke:#4C8B6B,color:#172B4D;
    classDef blocked fill:#FFE4E1,stroke:#A35D57,color:#172B4D;
    class U start;
    class D,M,S,Q,C action;
    class R gate;
    class W success;
    class F blocked;
```

## Start

1. Resolve a platform application-data directory or an explicit `--data-dir`.
2. Create owner-controlled state and configure SQLite inside it.
3. Apply migrations before accepting requests.
4. Bind FastAPI to loopback on the requested or a dynamic port.
5. Write readiness metadata only after the server and bundled UI respond.
6. Open the local UI unless `--no-browser` is set.

```bash
.venv/bin/proofline launch
.venv/bin/proofline launch --no-browser --port 0
```

## Stop

SIGINT/SIGTERM and the desktop private shutdown endpoint request graceful server termination. The
ready file is removed after clean shutdown. The private token is process-local and must not appear
in logs or public API responses.

## Desktop wrapper

The Tauri application starts the target-specific frozen sidecar, waits for its readiness file, and
navigates its webview to the same-origin loopback UI. It kills the child only when graceful shutdown
cannot complete. The current macOS package is unsigned and experimental.

## Failure states

Migration, bind, readiness, sidecar, and browser-open failures are explicit. A stale readiness file
does not prove a live server. No lifecycle receipt proves installer signing, uninstall, upgrade,
rollback, Windows behavior, or production readiness unless those observations are recorded on the
target platform.
