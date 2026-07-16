# DEP v1 test vectors

`valid-minimal.json` is a complete deterministic-package fixture. A conforming verifier must
return the values in `expected.json`.

`mutations.json` defines invalid transforms as JSON Pointer replacements applied to a fresh copy of
`valid-minimal.json`. A conforming verifier must reject each mutation with the listed content-free
error code. Error wording is implementation-specific; the stable code is normative for Proofline's
reference verifier.

Run the reference vectors from the repository root:

```bash
proofline verify-package spec/decision-evidence-package/v1/test-vectors/valid-minimal.json
pytest -q apps/api/tests/test_dep_format.py
```
