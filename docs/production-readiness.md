# Production readiness

Status: **not production-ready**. This document is the evidence gate for changing that claim.
Implementation alone does not close a gate; each required row needs a versioned receipt or an
externally verifiable release record.

## Target production profile

The first supported production profile is deliberately narrow:

- one local user on a supported macOS or Windows machine;
- a signed desktop distribution supervising the bundled loopback API and web UI;
- local SQLite state in an application-owned data directory;
- deterministic/offline operation by default, with explicitly configured local or remote models;
- operator-owned encrypted backup and tested recovery.

Hosted multi-user deployment, public internet exposure, mobile clients, managed sync, SSO and team
collaboration are separate future profiles. They do not silently inherit readiness from the local
profile.

## Gate matrix

| Area | Required evidence | Status | Current evidence or blocker |
| --- | --- | --- | --- |
| Public repository | License, community docs, current support policy, no contributor-machine paths, accurate implemented/planned claims | Complete for experimental pre-alpha | `thangldw/proofline` is public with license, conduct, contribution, security, support and maintainer documents |
| Reproducible release | Versioned source, wheel, bundled web archive, checksums, clean installed-package smoke | Complete for local macOS | `v0.14.14` GitHub assets and checksummed platform receipt |
| macOS lifecycle | Install, start, readiness, same-origin UI, migration, graceful stop, integrity and recovery | Complete for installed wheel | `v0.14.14` installed-release receipt plus platform-aware wheel launcher; native signing remains a separate gate |
| Windows lifecycle | Same installed-artifact and recovery path on a real Windows target | Blocked | No Windows runner or machine receipt |
| Native packaging | Signed macOS and Windows installers, application data paths, uninstall behavior and update rollback | Partial | Experimental Tauri `.app/.dmg` builds locally; macOS notarization, real Windows installers, uninstall and updater rollback receipts remain open |
| Data integrity | Versioned migrations, immutable source identity, exact spans, deletion cascade and semantic verification | Complete for tested local schema | Migration, provenance, deletion and integrity suites |
| Backup/recovery | Encrypted retention policy plus successful backup, restore and rollback drills from release artifacts | Partial | `v0.14.14` receipt proves atomic restore and rollback from the installed artifact; encrypted retention policy remains operator-owned and unqualified |
| Offline core | Useful ingestion, retrieval, memory review and Studio behavior without external services | Complete for deterministic scope | Credential-free regression and UI suites |
| Model quality | Frozen real corpus, pinned local/remote models, extraction/citation/abstention/latency/cost report | Blocked | Only `mock_integration` evidence exists |
| External utility | Permissioned pilot with at least 25 questions, temporal cases, baseline and useful-answer metrics | Blocked | Templates exist; no external pilot evidence |
| Provider secrets | Per-device secure storage, rotation/removal and no inclusion in logs, exports or backups | Complete on macOS; Windows receipt pending | `v0.14.14` launcher defaults to OS keyring on macOS/Windows; macOS installed-wheel receipt exercises set/read/delete |
| Operational support | Supported versions, issue handling, upgrade/rollback policy, data-loss escalation and release cadence | Complete for pre-alpha; production commitments blocked | `SUPPORT.md` names current best-effort policy and rollback flow; `MAINTAINERS.md` records unassigned signing, updater and incident-response ownership |
| Security qualification | Threat-boundary verification and release security assessment | Blocked | Explicitly excluded from the current work scope; production claim is impossible while excluded |

## Claim rules

- `public experimental pre-alpha` requires only the public-repository hygiene gate plus accurate
  pre-alpha warnings.
- `alpha` requires every criterion in `alpha-support-boundary.md` with versioned evidence.
- `production-ready local desktop` requires every non-out-of-scope row above to be Complete.
- A mock provider, synthetic corpus, source-development test or implementation screenshot cannot
  substitute for a real platform, model, pilot, recovery or security receipt.

## Next execution order

1. Keep public metadata, support boundaries and implemented/planned claims accurate in each release.
2. Qualify and sign/notarize the implemented desktop wrapper and define updater rollback.
3. Obtain a real Windows environment, build MSI/NSIS there and close the same receipt contract.
4. Run the frozen real-model comparison and external pilot.
5. Complete security qualification before changing the production claim.
