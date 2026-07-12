# ADR-001: Event transport for the ingestion pipeline

Date: 2026-07-12

## Context

The first release runs on one machine and processes fewer than 10,000 source updates per day. The team needs jobs to survive process restarts without operating a separate cluster.

## Decision: Use a SQLite-backed job queue for the local MVP

Rationale: SQLite keeps local installation simple, provides transactional state changes, and is sufficient for the measured workload.
Status: active

## Consequences

Workers lease jobs from the database. We will retain a queue interface so that a hosted deployment can later use NATS without changing ingestion code.

## Rejected alternative

Kafka was rejected for the local MVP because its operational cost is disproportionate to the initial workload.

