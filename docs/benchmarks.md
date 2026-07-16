# Reproducible benchmarks

The Decision Evidence Package benchmark exercises the same credential-free local paths used by the
product: deterministic Markdown ingest into SQLite, decision/evidence extraction, package build,
in-memory verification, canonical JSON sizing, deterministic ZIP sizing, and Python peak-memory
tracking.

Reproduce it with:

```bash
make benchmark-evidence-package
```

The command writes `evals/benchmarks/decision-evidence-package-v1.json` and records the Python
version, platform, timestamp, fixture identity, and iteration count. The committed 2026-07-16
macOS ARM64 / CPython 3.14.6 receipt reports:

| Metric | Result |
| --- | ---: |
| Ingest latency | 52.29 ms |
| Package build latency | 8.02 ms |
| Median verify latency (100 iterations) | 0.35 ms |
| Canonical JSON size | 3,613 bytes |
| Deterministic ZIP size | 3,737 bytes |
| Peak traced Python memory | 1,995,756 bytes |

These values describe one synthetic local ADR fixture on the recorded machine. Database migration
time is excluded. The receipt does not establish production capacity, representative corpus scale,
model performance, connector performance, or cross-platform parity. Compare receipts only when the
fixture schema, implementation revision, environment, and command are recorded together.

The separate provenance-scale benchmark (`make benchmark-provenance`) measures parser, SHA-256,
and exact-span behavior at synthetic 1K/10K/100K counts. It does not replace the package benchmark
or qualify database/retrieval scale.
