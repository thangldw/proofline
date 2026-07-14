# ADR: Local ingestion queue

## Context

Proofline runs as a single-user local application. Ingestion jobs must survive process restarts
without requiring another service.

## Decision: Keep ingestion jobs in SQLite

Rationale: SQLite provides transactional state and recovery inside the existing local database.
Status: active

## Assumption: One local runtime owns writes

Rationale: The current supported experiment has one user and one supervised application runtime.

## Constraint: Local development works without infrastructure

Rationale: Deterministic ingestion, retrieval, and review must run without credentials or external
services.

## Alternative: Operate a separate message broker

Rationale: A broker adds deployment and recovery cost that the current local workload does not
justify.
Status: rejected

## Consequence

Workers lease jobs from SQLite. A future hosted profile may implement the queue interface with a
managed broker, but it cannot change historical source identity or evidence spans.
