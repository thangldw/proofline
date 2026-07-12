# ADR-E2E: Local queue ownership

## Decision: Use SQLite for the local job queue
Rationale: It provides transactional recovery without another service.
Status: active

Assumption: A single writer owns the local database.
Rationale: The desktop process serializes queue mutations.

The following hostile markup is test data and must remain inert text:
<script>window.__prooflineE2ECompromised = true</script>
<img src=x onerror="window.__prooflineE2ECompromised = true">
