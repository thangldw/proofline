# ADR 0001: Local evidence-first vertical slice

Status: accepted.

Proofline uses Python/FastAPI, SQLite/FTS5, React, and an optional Tauri wrapper for a single-user
local application. This stack keeps deterministic ingestion, migrations, retrieval, backup, and
exact provenance usable without external services.

```mermaid
flowchart TB
    T["Tauri · optional shell"] --> W["React · bundled UI"]
    W --> A["FastAPI · local API"]
    A --> D["SQLite + FTS5 · authority"]

    classDef shell fill:#EEE4FF,stroke:#765E9C,color:#172B4D;
    classDef ui fill:#DDEBFF,stroke:#5B7DB1,color:#172B4D;
    classDef api fill:#DDF7EA,stroke:#4C8B6B,color:#172B4D;
    classDef data fill:#FFF4C2,stroke:#7A6F45,color:#172B4D;
    class T shell;
    class W ui;
    class A api;
    class D data;
```

The first product boundary excludes collaboration, hosted sync, broad connectors, rich editing,
canvas, graph databases, generic agents, and autonomous source write-back. New surfaces must extend
the immutable source/version/span contract rather than bypass it.
