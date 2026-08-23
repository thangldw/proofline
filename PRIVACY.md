# Privacy Policy

Last updated: 2026-08-23

Proofline and its bundled plugin are local-first. The project does not operate a hosted Proofline service, create user accounts, collect telemetry, or transmit sources, decisions, citations, evidence packages, local paths, or credentials to the project author.

Proofline stores user-selected sources, decisions, provenance metadata, and derived indexes in local user-controlled storage. It writes exports, evidence packages, reports, and backups only to paths selected by the user. Users control retention through Proofline's local data directory and exported files.

Signed attestation keys and envelopes remain local. Proofline reads a private key only for an explicitly invoked signing command, does not store it in SQLite or plugin assets, and includes only a public-key identifier and signature in the envelope.

Optional model or embedding providers may receive selected content only when the user configures and invokes them. Their privacy terms apply to those calls. Proofline does not enable external providers automatically and does not embed provider credentials.

For privacy questions, open an issue at https://github.com/thangldw/proofline/issues.
