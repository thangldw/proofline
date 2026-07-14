# Backup and recovery

Use only recoverable test data. Keep verified backups outside the active application-data directory.

```mermaid
flowchart LR
    L["Live database"] --> B["Create backup"]
    B --> V{"Verify"}
    V -->|pass| S["Store outside app data"]
    V -->|fail| X["Discard + investigate"]
    S --> R["Restore candidate"]
    R --> C["Create rollback copy"]
    C --> A["Atomic replace"]
    A --> I{"Integrity check"}

    classDef data fill:#FFF4C2,stroke:#7A6F45,color:#172B4D;
    classDef action fill:#DDEBFF,stroke:#5B7DB1,color:#172B4D;
    classDef gate fill:#FDE1EF,stroke:#9C5E7B,color:#172B4D;
    classDef safe fill:#DDF7EA,stroke:#4C8B6B,color:#172B4D;
    classDef blocked fill:#FFE4E1,stroke:#A35D57,color:#172B4D;
    class L,B,R,C,A action;
    class V,I gate;
    class S safe;
    class X blocked;
```

## Create and verify

```bash
.venv/bin/proofline backup --output /safe/path/proofline.db
.venv/bin/proofline verify-backup /safe/path/proofline.db
.venv/bin/proofline verify-integrity
```

Backup uses SQLite's consistent backup mechanism and refuses accidental overwrite unless `--force`
is supplied. Verification checks the database structure and Proofline provenance contracts without
publishing source content.

## Restore

Stop Proofline before restoring. Verify the candidate, choose a rollback path outside the active
database, then run:

```bash
.venv/bin/proofline restore-backup /safe/path/proofline.db \
  --rollback-output /safe/path/proofline-before-restore.db
```

Restore rejects the active database path, SQLite sidecars, invalid schema, and unsafe path overlap.
It writes a rollback copy before atomically replacing the active database and performs post-restore
verification. Preserve both files until the application has been exercised successfully.

## Portable transfer

```bash
.venv/bin/proofline export --output /safe/path/proofline.json
.venv/bin/proofline verify-export /safe/path/proofline.json
.venv/bin/proofline import /safe/path/proofline.json
```

Import into a non-empty database requires preview plus explicit merge with the preview SHA-256.
Merge remaps identifiers deterministically and rolls back atomically on failure; it never performs a
destructive overwrite.
