# Contributing to Proofline

Proofline is in its foundation phase. Before proposing a large feature, read
the product brief, architecture, ADRs, and current roadmap in `docs/`.

## Workflow

1. Start from a narrowly scoped issue with observable acceptance criteria.
2. Keep schema and API changes backward-compatible or include a migration.
3. Add tests that prove provenance and deletion behavior where relevant.
4. Run `make check` and `make test` before opening a pull request.
5. Update documentation when behavior or configuration changes.

Pull requests should explain the user problem, the chosen boundary, how the
change was verified, and any known limitations. Avoid bundling unrelated
refactors with product behavior.

## Security and privacy

Treat all ingested content as sensitive. Do not include real user data in
fixtures, logs, screenshots, or bug reports. Please report security issues
privately as described in `SECURITY.md`.

