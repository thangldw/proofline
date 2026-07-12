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
