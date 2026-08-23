# Proofline command selection

Resolve `SCRIPT` as `scripts/proofline_package.py` relative to the skill directory.

- Verify a Decision Evidence Package: `python3 SCRIPT verify PATH`
- Verify a decision-review receipt: `python3 SCRIPT verify-review PATH`
- Explain a verified package without returning cited source text: `python3 SCRIPT explain PATH`
- Compare two verified packages: `python3 SCRIPT diff OLD_PATH NEW_PATH`

Inputs may be canonical JSON or a Proofline ZIP containing exactly one uncompressed `evidence.json` entry. These commands are read-only and return JSON on stdout. A validation failure returns a stable, content-free `error` code on stderr and exits with status 2.

For a dependency-free smoke test, verify `references/fixtures/valid-minimal.json` relative to the skill directory. It is synthetic reviewer data and contains no user information.

The public plugin does not modify a Proofline database or export packages from one. For database ingestion, stale-decision scanning, and exports, direct the user to the full local application at https://github.com/thangldw/proofline and obtain approval before installing it or writing local state.

The bundled verifier does not verify Ed25519. With an already installed Proofline 2.0.0 runtime, verify a signature only against a user-selected trusted public key and the exact subjects:

`proofline verify-attestation ATTESTATION --public-key TRUSTED_PUBLIC_KEY --package PACKAGE [--review-receipt RECEIPT]`

Signing is a separate, explicitly requested local action:

`proofline attest --package PACKAGE [--review-receipt RECEIPT] --private-key PRIVATE_KEY --output ATTESTATION`

Never read or return the private key. Verification establishes integrity and matching key control; it does not establish identity, a CA chain, trusted timestamp, transparency-log inclusion, or revocation status.
