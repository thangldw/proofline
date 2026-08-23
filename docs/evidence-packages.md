# Evidence package formats

Proofline has two independent, canonical JSON contracts.

`proofline-decision-evidence-package-v1` captures the immutable source version, exact cited spans,
transformation lineage, decision content and historical decision status. Its root hash proves package
integrity, not authenticity. It is not a signature and does not identify the person who approved the
decision.

`proofline-decision-review-receipt-v1` binds a deterministic stale-evidence finding and its review
state to the original package root. It contains UUIDs, SHA-256 hashes, anchor state, policy hash,
resolution and timestamps; it deliberately excludes source and quote content. An accepted decision
can therefore remain historical fact while its separate review state is open: “Accepted · review
required.”

Verify both without database or AI-provider access:

```bash
proofline verify-package evidence.zip
proofline verify-review-receipt decision-review.json
python skills/manage-evidence-decisions/scripts/proofline_package.py verify evidence.zip
python skills/manage-evidence-decisions/scripts/proofline_package.py verify-review decision-review.json
```

The schema and mutation vectors live under `spec/decision-evidence-package/v1/` and
`spec/decision-review-receipt/v1/`. Verification is fail-closed with stable, content-free error
codes. Portable export v3 preserves review rows and active/superseded evidence chains; v1 and v2
exports receive deterministic anchor backfill during verification/import.

Current scope is a single-user local-first workflow. Hash verification does not provide signatures,
identity, authorization, hosted sync, shared workspace consistency or connector trust. Preserve the
original package and review receipt together when transferring evidence.
