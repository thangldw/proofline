# Alpha release criteria and support boundary

Proofline remains pre-alpha through the current `v0.14.9` release. Versioned GitHub artifacts are
stable snapshots of their documented behavior, but they do not carry production support,
compatibility, uptime, or data-loss guarantees.

## Current supported experiment

- One local user and one or more local workspaces on a developer-controlled machine.
- Python 3.11+ wheel plus the bundled same-origin web UI, bound to loopback by default.
- Local SQLite state under an explicitly owned data directory.
- Markdown, UTF-8 text, registered folders, and explicitly registered local Git repositories.
- Deterministic ingestion, search, exact evidence, governed memory, export, backup, verification,
  and portable import/merge without requiring an external service.
- macOS and Linux development use. The latest recorded hosted matrix covers macOS and Ubuntu for an
  older revision; `v0.14.9` itself is qualified by a versioned local macOS release receipt covering
  install, lifecycle, portability, backup, integrity and OS-keyring behavior.

Use only approved, recoverable test data. Keep a verified backup outside the active data directory
before migrations, restore drills, upgrades, or packaging experiments.

## Explicitly unsupported

- Production workloads, availability commitments, regulated or irreplaceable data.
- Windows support until the installed-wheel platform smoke passes on a real Windows environment.
- Signed native installers, automatic updates, rollback orchestration, mobile capture, or app-store
  distribution.
- Multi-device sync, hosted backup, authentication, RBAC, shared/team workspaces, or internet-facing
  deployment.
- General real-model quality claims, pilot adoption claims, and unattended write-back to sources.
- Compatibility guarantees across pre-alpha schema, CLI, API, or portable-export revisions beyond
  the explicit migration and verifier contracts in each release.

## Criteria to call a future build “alpha”

All items must have versioned evidence rather than an implementation-only assertion:

1. Installed-wheel smoke passes on current supported macOS, Ubuntu, and Windows targets.
2. One-command local startup, readiness, same-origin UI, graceful stop, migration, backup, restore,
   and rollback drills pass from release artifacts.
3. A permissioned external corpus contains at least 25 questions, including 10 temporal-decision
   questions, with frozen relevance judgments and model/provider configuration.
4. Citation precision is at least 90% and useful-answer rate at least 65% on that corpus; synthetic
   regression metrics do not satisfy this criterion.
5. At least three design partners complete the documented install/upgrade/recovery path, and every
   blocking failure has an owner or an explicit exclusion.
6. Supported OS/Python versions, issue response expectations, backup responsibility, migration
   policy, release rollback, and data-loss escalation are named in the release notes.
7. Installer signing and update rollback have named owners before any native desktop build is
   presented as supported.

## Support and issue handling

GitHub Issues are the public defect and feature channel. There is no SLA. Reports must include the
Proofline version, OS/Python version, safe reproduction steps, and content-free diagnostics; do not
attach source documents, database files, provider keys, prompts, or private model payloads. Security
reports follow `SECURITY.md` rather than public issues.

The project may fix or narrow a pre-alpha behavior instead of preserving compatibility. Release
notes must describe the change, and persistent changes still require migrations and recovery
guidance.
