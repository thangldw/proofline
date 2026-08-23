# Evidence package formats

Proofline has three independent, canonical JSON contracts.

`proofline-decision-evidence-package-v1` captures the immutable source version, exact cited spans,
transformation lineage, decision content and historical decision status. Its root hash proves package
integrity, not authenticity. It is not a signature and does not identify the person who approved the
decision.

`proofline-decision-review-receipt-v1` binds a deterministic stale-evidence finding and its review
state to the original package root. It contains UUIDs, SHA-256 hashes, anchor state, policy hash,
resolution and timestamps; it deliberately excludes source and quote content. An accepted decision
can therefore remain historical fact while its separate review state is open: “Accepted · review
required.”

`proofline-signed-attestation-v1` signs a canonical statement containing the package root and
artifact ID plus an optional bound review-receipt hash. Verification requires the exact package,
the optional receipt when present, and a trusted Ed25519 public key selected independently from the
artifact. The signed statement also binds the Ed25519 algorithm, raw-public-key SHA-256 key ID and
canonical RFC 3339 UTC issuance time using `Z`, with zero fractional seconds omitted and any
fraction limited to microseconds with trailing zeros omitted. The private key is never included in
the envelope.

Verify both without database or AI-provider access:

```bash
proofline verify-package evidence.zip
proofline verify-review-receipt decision-review.json
python skills/manage-evidence-decisions/scripts/proofline_package.py verify evidence.zip
python skills/manage-evidence-decisions/scripts/proofline_package.py verify-review decision-review.json
```

Create and verify an attestation with the full Proofline 2.0.0 runtime:

```bash
key_dir="${PROOFLINE_KEY_DIR:?set PROOFLINE_KEY_DIR outside repositories and synced folders}"
install -d -m 700 "$key_dir"
proofline generate-attestation-key \
  --private-key "$key_dir/signing.pem" --public-key "$key_dir/signing.pub.pem"
proofline attest --package evidence.zip --review-receipt decision-review.json \
  --private-key "$key_dir/signing.pem" --output attestation.json
proofline verify-attestation attestation.json --public-key "$key_dir/signing.pub.pem" \
  --package evidence.zip --review-receipt decision-review.json
```

`generate-attestation-key` enforces owner-only descriptor permissions and fails closed with
`secure_permissions_unsupported` where that primitive is unavailable, including CPython 3.12 on
Windows. On such hosts, provision an Ed25519 PKCS#8 key with an owner-only Windows ACL using an
external key-management workflow, then use `attest` and `verify-attestation`. Signed envelopes are
bounded to 1 MiB; a larger DEP artifact ID is rejected before output.

The schema and mutation vectors live under `spec/decision-evidence-package/v1/` and
`spec/decision-review-receipt/v1/`. Verification is fail-closed with stable, content-free error
codes. Portable export v3 preserves review rows and active/superseded evidence chains; v1 and v2
exports receive deterministic anchor backfill during verification/import.

The signed schema and fixed Ed25519 vector live under `spec/signed-attestation/v1/`. A valid
signature establishes integrity and control of the matching private key relative to the trusted
public key. It does not establish legal identity, a CA trust chain, trusted timestamp,
transparency-log inclusion, key revocation, authorization or artifact safety.

Current scope is a single-user local-first workflow. Preserve the original package, review receipt,
attestation and independently trusted public key together when transferring evidence.
