<!-- Executable source fixture: intentionally English-only to preserve exact-span cardinality. -->

# ADR-E2E: Offline import queue

## Decision: Use an embedded queue for offline imports
Rationale: It provides transactional recovery without another service.
Status: active

Assumption: A single local worker owns queue mutations.
Rationale: The desktop runtime serializes writes to the evidence database.

The following hostile markup is test data and must remain inert text:
<script>window.__prooflineE2ECompromised = true</script>
<img src=x onerror="window.__prooflineE2ECompromised = true">
