# Documentation

These documents describe the current v1.0.0 codebase and completed provenance vertical slice. The active
set is organized around one contract: every derived claim resolves to an immutable source identity
and exact source span. Historical implementation detail belongs in Git history and release notes.

| Document | Purpose |
| --- | --- |
| [Product brief](product-brief.md) | Problem, promise, user hypothesis, scope, and product priority |
| [Architecture](architecture.md) | Runtime components, data flow, and invariants |
| [Visual language](visual-language.md) | Offline typography and collaborative-canvas diagrams |
| [Provider configuration](provider-configuration.md) | Local/remote model settings and secret storage |
| [Embedded lifecycle](embedded-lifecycle.md) | Launcher and desktop process contract |
| [Backup and recovery](backup-recovery.md) | Backup, verification, restore, and rollback |
| [Decision Evidence Packages](evidence-packages.md) | Merkle DAG, artifact explanation, hashing, and offline verification |
| [Provenance phase closeout](phase-closeout-2026-07.md) | Closed scope, verification evidence, deferrals, and reopening criteria |
| [Pilot protocol](pilot-protocol.md) | Permissioned external evaluation procedure |
| [Production readiness](production-readiness.md) | Evidence gates and current blockers |
| [Alpha support boundary](alpha-support-boundary.md) | Supported experiment and alpha criteria |
| [Windows release](windows-release.md) | Real-Windows build and receipt workflow |
| [v1.0.0 release](releases/v1.0.0.md) | Current published release notes |

Architecture decisions are under [`adr/`](adr/). The executable backlog is
[`NEXT_STEPS.md`](../NEXT_STEPS.md).
