# Proofline evaluations

Evaluation datasets are versioned inputs, not product marketing claims.

`retrieval/seed-v1.json` is a synthetic regression corpus. It proves that the evaluation runner,
real SQLite migrations, ingestion, and retrieval can be reproduced in CI. It deliberately includes
three paraphrase queries with no lexical overlap so the baseline records the known gap that semantic
retrieval must close.

Run the current gate with:

```bash
make eval
```

The dataset records graded relevance at source URI level. The runner reports Recall@k,
Precision@k, reciprocal rank, and nDCG@k after deduplicating chunk hits by source. Add a new dataset
version instead of rewriting historical judgments.

The synthetic corpus does not satisfy the roadmap requirement for at least 25 real pilot questions.
That dataset must be collected with permission, sanitized, labeled with source evidence, and marked
with non-synthetic provenance before it can support product-quality or go/no-go claims.

## Local lexical benchmark

The CLI can measure SQLite FTS5 query latency against a generated, deterministic, temporary
fixture without using a network or model provider:

```bash
proofline benchmark --sources 1000 --queries 100
```

The report identifies the fixture version and provenance, source/chunk/query counts, matched query
count, result limit, and per-query p50, p95, and maximum latency in milliseconds. The temporary
database is deleted after the run. Change `--sources`, `--queries`, or `--limit` to describe a
different local measurement explicitly.

This command records an environment-specific measurement; it does not enforce a latency threshold
and is not evidence for the roadmap's 10,000-file scale target. Any published comparison must also
record the Proofline revision, operating system, SQLite/Python versions, hardware, fixture arguments,
and whether other workloads were active.

Committed observations live in [`benchmarks/`](./benchmarks/) and include the exact Proofline
revision, environment, command, fixture provenance, and qualification. They are receipts for a
specific run, not portable performance guarantees.
