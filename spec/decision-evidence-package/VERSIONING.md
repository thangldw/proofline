# Versioning policy

DEP uses an integer major version in both its schema identity
(`proofline-decision-evidence-package-v1`) and specification directory (`v1`).

- A major version is immutable after release. Existing required fields, canonicalization, hash
  domains, node semantics, archive layout, and verification behavior do not change in place.
- Any change that can alter a valid package root, make a v1 package invalid, add a required field,
  or change a field's meaning requires a new major version and a new schema identity.
- Clarifications, additional invalid test vectors, editorial fixes, and verifier hardening that
  rejects inputs already invalid under the written v1 contract may be added without a new major.
- Consumers must reject unknown major versions. Producers should continue offering the previous
  major during a documented transition and must never silently rewrite an exported package.
- Extensions are not permitted inside v1 objects because every object is closed. Experimental
  metadata must live outside the package until standardized in a new major version.

Proofline v1 provides integrity and lineage, not signatures, source authenticity, identity trust,
revocation, or trusted timestamps. Adding any of those trust semantics requires a threat model and
will not be retroactively claimed for v1 packages.
