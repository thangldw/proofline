# Maintainers

Current maintainer: **Thang Luu** (`thangldw`).

The maintainer owns repository policy, release decisions, migrations, support boundaries, and public
claims. Production signing, notarization, updater rollback, Windows qualification, incident
response, and commercial operations do not yet have qualified owners.

Releases are experimental pre-alpha snapshots. A release must come from a clean `main`, pass the
local quality gate, use a `[skip ci]` commit while GitHub Actions quota is unavailable, and publish
checksummed artifacts and receipts directly with GitHub CLI.
