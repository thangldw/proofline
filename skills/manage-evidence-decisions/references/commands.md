# Proofline command selection

- Self-contained product story: `.venv/bin/proofline demo stale-decision`
- Verify a Decision Evidence Package: `.venv/bin/proofline verify-package PATH`
- Explain a stored memory artifact: `.venv/bin/proofline explain ARTIFACT_ID`
- Compare two packages: `.venv/bin/proofline diff OLD_PATH NEW_PATH`
- Check stored decisions for changed evidence: `.venv/bin/proofline check-decisions`
- Export a package: run `.venv/bin/proofline export-package --help` and provide the artifact ID and a new output path.
- Verify a portable export: `.venv/bin/proofline verify-export PATH`

Run `.venv/bin/proofline COMMAND --help` before unfamiliar or write-capable operations. Prefer a new output path; use `--force` only with explicit overwrite approval.
