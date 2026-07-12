# Contributing to Proofline

Proofline is in its foundation phase. Before proposing a large feature, read
the product brief, architecture, ADRs, and current roadmap in `docs/`.

Participation is governed by the [Code of Conduct](CODE_OF_CONDUCT.md). Use the
structured GitHub issue forms for bugs and scoped feature requests, and report
suspected vulnerabilities privately through [SECURITY.md](SECURITY.md).

## Workflow

1. Start from a narrowly scoped issue with observable acceptance criteria.
2. Keep schema and API changes backward-compatible or include a migration.
3. Add tests that prove provenance and deletion behavior where relevant.
4. Run `make check` and `make test` before opening a pull request.
5. Update documentation when behavior or configuration changes.
6. Add a concise entry to [CHANGELOG.md](CHANGELOG.md) for notable user-visible,
   operator-visible, compatibility, migration, or security changes.

Pull requests should explain the user problem, the chosen boundary, how the
change was verified, and any known limitations. Avoid bundling unrelated
refactors with product behavior.

## Security and privacy

Treat all ingested content as sensitive. Do not include real user data in
fixtures, logs, screenshots, or bug reports. Please report security issues
privately as described in `SECURITY.md`.
