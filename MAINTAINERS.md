# Proofline maintainers and ownership

## Current maintainer

- [@thangldw](https://github.com/thangldw) — repository maintenance, architecture decisions,
  pre-release publication and best-effort issue triage.

Changes to provenance, persistence, provider boundaries, packaging or support policy require an
ADR or an explicit update to an accepted ADR. Release claims require the evidence described in
[Production readiness](docs/production-readiness.md).

## Ownership gaps

The following production responsibilities are deliberately unassigned:

- macOS Developer ID signing and notarization;
- Windows code signing and installer qualification;
- desktop updater ownership and tested application rollback;
- production incident response and response-time commitments;
- encrypted-backup retention operations;
- real-model evaluation dataset stewardship; and
- external pilot recruitment and ongoing support.

Until named owners accept these responsibilities and versioned evidence exists, Proofline remains
pre-alpha and must not be presented as a supported production desktop application.
