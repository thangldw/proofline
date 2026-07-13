# Roadmap evidence audit — 2026-07-13

This audit separates implemented repository work from milestones that require external systems,
credentials, participants or legal decisions. Planned behavior is not counted as shipped.

## Implemented and released

- v0.3.0: immutable read-only local Git ingestion.
- v0.4.0: temporal decision relations.
- v0.5.0: provider configuration and reliability.
- v0.6.0: reranking, grounding assessment and vector candidate indexing.
- v0.7.0: workspace isolation and multi-worker folder-scan leases.
- v0.8.0: previewed portable merge/remap into non-empty databases.
- v0.9.0: workspace UI and benchmark-backed watcher decision.
- v0.9.1: bright Sky + Mint visual system and responsive navigation fixes.
- v0.10.0: embedded start/readiness/stop, owned data directory and same-origin web serving.
- v0.11.0: reviewed web UI bundled in the installed wheel with clean-environment server smoke.

## Technically open

- Windows verification: blocked by exhausted hosted Actions quota and no real Windows machine in
  the current workspace. Static review or emulation is not equivalent evidence.
- Production packaging: the embedded lifecycle and one-command wheel are implemented and locally
  tested, but
  Docker is unavailable on the current machine and no installer is signed; no production support
  claim can be made.

The [receipt quality report](./reports/roadmap-evidence-quality-v0.10.0.html) found that all six
checked-in receipts qualify their scope, while only three include timestamps and three include the
tested revision. Future receipt writers should normalize that metadata before trend comparisons.

## External evidence gates

- Real-model comparison requires selected remote/local model runtimes, credentials where applicable,
  locked model versions and permission to incur inference cost.
- Pilot and go/no-go metrics require 5 design partners, 5–10 interviews, at least 25 permissioned
  questions and repeated weekly usage. Synthetic fixtures cannot satisfy these gates.
- P2 connectors remain gated by the roadmap's pilot-value condition. Implementing the connector
  matrix before that evidence would violate the repository scope instructions.
- ICP, paid surface, license change, trademark and willingness-to-pay decisions require product,
  customer or legal evidence outside the repository.

## Resume criteria

When Actions quota or a Windows machine becomes available, run the installed wheel through
`scripts/platform_smoke.py` and save a versioned receipt under `evals/platform/`. When Docker becomes
available, build Compose, wait for health, run seed/search/backup/restore, restart the service and
record persistence and recovery results. Only then reconsider production qualification.
