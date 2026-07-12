# Data export, backup, and recovery

Status: **Implemented for the local SQLite deployment.** The commands in this
document are covered by automated integrity and recovery tests. They do not
replace an operator-owned backup retention, encryption, or disaster-recovery
policy.

## Choose the right artifact

Proofline produces two different artifacts:

| Artifact | Purpose | Contains | Does not contain |
| --- | --- | --- | --- |
| Portable JSON export | Inspectable, provider-neutral knowledge snapshot | immutable source versions, governed memories, exact evidence, safe model-run lineage, relevant audit and terminal ingestion metadata | derived chunks/indexes/embeddings, private staged retry inputs, credentials, prompts; import is not implemented |
| SQLite backup | Exact recovery of the current local deployment | the complete SQLite database, including source contents, historical versions, indexes, embeddings, audit data, model metadata, and staged ingestion inputs | external files or secrets stored outside SQLite |

The portable export is **not a restorable backup** in the current pre-alpha.
Its SHA-256 manifest detects accidental modification and the verifier checks
internal references and exact evidence spans; it is not a digital signature or
proof of authenticity.

## Create and verify a portable export

Run commands from the repository root after `make setup`:

```bash
.venv/bin/proofline export --output proofline-export.json
.venv/bin/proofline verify-export proofline-export.json
```

Both export and backup refuse to overwrite an existing output unless `--force`
is supplied. Output files are created with owner-only permissions (`0600`).

## Create and verify a SQLite backup

```bash
.venv/bin/proofline backup --output proofline-backup.db
.venv/bin/proofline verify-backup proofline-backup.db
```

The backup command uses SQLite's online backup API, so it takes a consistent
snapshot while the API can remain available. Before publishing the file,
Proofline checks database integrity, foreign keys, required tables, and the
exact current migration set. Verification is read-only and does not initialize
or migrate the candidate database.

The backup contains sensitive source text and may contain private staged retry
payloads, request identifiers, and embeddings. File permissions are not
encryption. Encrypt backups at rest, restrict access, and store keys separately.

## Restore a verified local backup

1. Verify the candidate with `proofline verify-backup` using the same Proofline
   version that will run it.
2. Stop the Proofline API and workers.
3. Preserve the current database as a separately named rollback copy.
4. Copy the verified backup to the SQLite path configured by
   `PROOFLINE_DATABASE_URL`, then set its mode to `0600`.
5. Start Proofline and check `/health`, source and memory counts, one known
   search, and the exact evidence span behind one known memory.
6. Keep the rollback copy until the restored deployment has been validated.

Example recovery drill using an isolated database path:

```bash
cp proofline-backup.db /tmp/proofline-recovery-drill.db
chmod 600 /tmp/proofline-recovery-drill.db
.venv/bin/proofline verify-backup /tmp/proofline-recovery-drill.db
PROOFLINE_DATABASE_URL=sqlite:////tmp/proofline-recovery-drill.db \
  .venv/bin/proofline serve
```

An online backup is a standalone SQLite database; do not copy a live database
file manually and do not restore stale `-wal` or `-shm` sidecar files. A backup
from a different schema version is rejected rather than silently migrated by
the verifier.

## Retention and deletion

Deleting a source removes its derived live records, but previously created
backups can still contain that data. Operators must define a retention window,
expire old backups, and securely destroy copies that are no longer authorized.
Test recovery periodically; creation without a successful restore drill is not
evidence that a backup is usable.
