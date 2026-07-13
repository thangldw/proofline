# Proofline support

Proofline is experimental pre-alpha software. Support is best effort, has no response-time or
resolution SLA, and covers only the default branch and latest GitHub pre-release. Older releases,
forks, production workloads, internet-facing deployments and irreplaceable data are unsupported.

## Supported experiment

- One local user running the latest installed wheel on a developer-controlled macOS machine.
- Python 3.11 or newer, bundled same-origin web UI, local SQLite and loopback binding.
- Credential-free deterministic behavior, plus explicitly configured providers under the
  boundaries documented in [Provider configuration](docs/provider-configuration.md).

Linux remains a development environment rather than a release-qualified desktop target. Windows
is unsupported until a real Windows installed-artifact receipt passes. Signed native installers,
automatic updates and application rollback are not available.

## Getting help or reporting a defect

Use [GitHub Issues](https://github.com/thangldw/proofline/issues) for reproducible defects and
feature proposals. Include only:

- Proofline version or Git revision;
- operating system, architecture and Python version;
- installation method and the exact content-free command that failed;
- expected and observed behavior;
- safe reproduction steps using synthetic data; and
- stable error codes or content-free diagnostics.

Do not attach source documents, databases, backups, provider keys, model prompts/responses,
personal data or proprietary repository content. Suspected vulnerabilities follow
[SECURITY.md](SECURITY.md), not a public issue.

## Data-loss escalation

If data may be damaged or missing:

1. Stop Proofline and do not retry writes against the affected data directory.
2. Preserve the directory and the most recent known-good encrypted backup locally; do not upload
   either artifact to an issue.
3. Record the version, last successful operation, stable error code and whether a rollback copy
   exists.
4. Run read-only verification only against a copy when possible.
5. Open a content-free issue. Ask for a private coordination channel before sharing any additional
   diagnostic that might disclose source material.

Recovery commands and invariants are documented in
[Data export, backup, and recovery](docs/backup-recovery.md). Backup encryption, retention, access
control and recovery testing remain the operator's responsibility.

## Upgrade and rollback policy

There is no compatibility guarantee between pre-alpha releases beyond documented migrations and
portable verification contracts. Before upgrading:

1. verify the release `SHA256SUMS`;
2. create and verify a fresh SQLite backup;
3. retain the previous wheel and a separately encrypted pre-upgrade backup; and
4. keep both until startup, `/health`, `verify-integrity` and one known exact-evidence workflow pass.

If validation fails, stop the new process, reinstall the previous wheel, and use
`proofline restore-backup` to restore the pre-upgrade database while preserving the failed state as
a new rollback copy. Do not open a database migrated by a newer version with an older version unless
that release explicitly documents backward compatibility.

## Release cadence

Proofline has no fixed release schedule during pre-alpha. A pre-release is published only after its
documented local tests, build, evaluations, installed-wheel smoke and checksum gates pass. Support
moves to the newest pre-release when it is published; there are no backport commitments.
