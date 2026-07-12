# Data export, backup, and recovery

Status: **Implemented for the local SQLite deployment.** The commands in this
document are covered by automated integrity and recovery tests. They do not
replace an operator-owned backup retention, encryption, or disaster-recovery
policy.

## Choose the right artifact

Proofline produces two different artifacts:

| Artifact | Purpose | Contains | Does not contain |
| --- | --- | --- | --- |
| Portable JSON export | Inspectable, provider-neutral knowledge snapshot and empty-database restore | immutable source versions, governed memories, exact evidence, safe model-run lineage, relevant audit and terminal ingestion metadata | embeddings, private staged retry inputs, credentials, prompts; merge/overwrite import is not implemented |
| SQLite backup | Exact recovery of the current local deployment | the complete SQLite database, including source contents, historical versions, indexes, embeddings, audit data, model metadata, and staged ingestion inputs | external files or secrets stored outside SQLite |

The portable export is restorable only into an empty initialized database. It is not an exact
replacement for the SQLite backup because private retry inputs, embeddings, and derived index IDs
are intentionally excluded. Its SHA-256 manifest detects accidental modification and the verifier
checks internal references and exact evidence spans; it is not a digital signature or proof of
authenticity.

## Create and verify a portable export

Run commands from the repository root after `make setup`:

```bash
.venv/bin/proofline export --output proofline-export.json
.venv/bin/proofline verify-export proofline-export.json
```

Both export and backup refuse to overwrite an existing output unless `--force`
is supplied. Output files are created with owner-only permissions (`0600`).

## Restore a portable export into an empty database

```bash
PROOFLINE_DATABASE_URL=sqlite:///./restored.db \
  .venv/bin/proofline import proofline-export.json
```

The importer verifies the size-bounded schema-v1 document before writing. It preserves exported
IDs and timestamps, rebuilds deterministic chunks and SQLite FTS rows without running extraction,
leaves embeddings empty for explicit re-indexing, and commits a unique receipt for the payload
hash. Any validation, constraint, indexing, or final payload-equivalence failure rolls back the
whole import.

A target containing any domain data, index rows, retry inputs, or previous import receipt fails
with `target_not_empty`. There is no merge, overwrite, `--force`, or ID-remapping mode. Source URIs
are preserved as provenance metadata and may refer to paths that do not exist on the new machine.
Terminal ingestion diagnostics preserve their historical `retryable` value for exact payload
fidelity, but excluded staged inputs cannot be recreated. Retrying one fails closed to
`dead_letter` with `ingestion_input_missing`; operators must re-ingest the authorized source.

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
