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

## Deterministic extraction regression gate

`extraction/seed-v1.json` is a synthetic credential-free corpus for the production deterministic
ingestion/extraction path. It covers decisions, assumptions, constraints, and alternatives; exact
status and statement matching; exact evidence slices and SHA-256 quote hashes; supported
English/Vietnamese markers; CJK statements after supported markers; headings; and negative prose
that must not be extracted.

Run the gate with:

```bash
proofline eval-extraction --dataset evals/extraction/seed-v1.json \
  --min-precision 1.0 --min-recall 1.0 --min-f1 1.0 \
  --min-evidence-resolution 1.0 --min-expected-evidence-accuracy 1.0 \
  --min-negative-source-accuracy 1.0
```

An extracted object matches an expectation only when source URI, memory kind, statement, and status
all match. The report uses micro object-level precision, recall, and F1. `evidence_resolution` is the
share of all extracted objects whose single persisted evidence record resolves to the same immutable
source/version, exact non-empty code-point span, quote, and quote hash.
`expected_evidence_accuracy` is the share of matched expected objects whose exact persisted quote
also matches the dataset expectation. `negative_source_accuracy` is the share of sources with no
expected memories that produced none. The report also records `model_run_count`; the gate requires
zero because this corpus exercises deterministic production extraction only.

These fixtures contain explicit synthetic markers and expected strings. A perfect score proves a
deterministic parser/provenance regression contract only; it is not evidence of real-model
extraction quality, semantic understanding, pilot precision/recall, or coverage of unmarked prose.

## Grounded-QA regression gate

`grounded-qa/seed-v1.json` is a synthetic, scripted regression corpus for the complete local answer
path. It runs real migrations, ingestion, lexical retrieval, context selection, `answer_question`,
structured-output validation, and server-side citation resolution. Its deterministic provider reads
the bounded user request and translates expected source titles to evidence IDs that Proofline issued
in that request. Missing evidence therefore reaches the normal unknown-citation repair/fail-closed
path; the evaluator does not inject citations directly into an answer.

Run it without credentials or network access:

```bash
proofline eval-grounded \
  --dataset evals/grounded-qa/seed-v1.json \
  --min-citation-resolution 1.0 \
  --min-citation-precision 1.0 \
  --min-grounded-success 1.0 \
  --min-status-accuracy 1.0
```

The report counts evidence IDs emitted by the scripted draft, citations resolved by the production
answer path, and resolved citations whose source URI is relevant according to the dataset. Aggregate
metrics are:

- `citation_resolution`: resolved citations divided by emitted citation IDs;
- `citation_precision`: relevant citations divided by resolved citations;
- `grounded_success`: expected-grounded queries that returned a grounded answer; and
- `expected_status_accuracy`: queries whose actual status matched the expected status.

Per-query output also records expected/actual statement kinds and model-run count. The explicit
insufficient-evidence fixture must create no model run. These values test deterministic contracts;
because statements and expectations are synthetic and scripted, they are not estimates of real-model
answer quality, pilot citation precision, useful-answer rate, or semantic entailment accuracy.

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
