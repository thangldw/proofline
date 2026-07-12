# Synthetic pilot simulation

This directory contains invented engineering context and scripted expectations used to exercise
the collection shape in the [external pilot protocol](../../docs/pilot-protocol.md). It is a
credential-free product-path regression, not a replacement for consented participant observation.

Run:

```bash
make simulate-pilot
```

To preserve a local receipt explicitly:

```bash
.venv/bin/python scripts/simulate_pilot.py \
  --dataset evals/pilot-simulation/engineering-context-v1.json \
  --output evals/pilot-simulation/receipts/local-YYYY-MM-DD.json
```

The runner uses a temporary SQLite database and the production migrations, ingestion, current-source
retrieval, bounded evidence selection, grounded-answer validation, and immutable citation spans. A
scripted provider emits only the expected statements and evidence IDs present in the bounded
production request; it uses no credentials and makes no network calls.

Reported `completed` means the scripted status and statement kinds matched, every emitted citation
resolved exactly, all resolved sources were expected, and the expected source set was covered.
Citation precision is relevance against the fixture's expected source URIs; it is not a human
entailment judgment. The deterministic naive baseline scans sources in sorted URI order and measures
source inspections only. Latency is an observation of the named local environment.

These outputs MUST NOT be counted toward real-question, temporal-question, useful-answer, weekly
adoption, willingness-to-pay, production-performance, or external-pilot citation gates. Receipts
with `+dirty` revisions describe an uncommitted working tree and remain development observations.
