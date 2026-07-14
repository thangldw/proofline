# Evaluations

Everything checked into `evals/` is synthetic or a target-specific development receipt. It protects
deterministic contracts and must not be presented as real-model, external-pilot, adoption, or
production-performance evidence.

```mermaid
flowchart LR
    F["Versioned fixture"] --> R["Production code path"]
    R --> M["Measured contract"]
    M --> G{"Threshold"}
    G -->|pass| C["Regression protected"]
    G -->|fail| X["Change blocked"]

    classDef fixture fill:#FFF4C2,stroke:#7A6F45,color:#172B4D;
    classDef process fill:#DDEBFF,stroke:#5B7DB1,color:#172B4D;
    classDef evidence fill:#DDF7EA,stroke:#4C8B6B,color:#172B4D;
    classDef gate fill:#FDE1EF,stroke:#9C5E7B,color:#172B4D;
    classDef blocked fill:#FFE4E1,stroke:#A35D57,color:#172B4D;
    class F fixture;
    class R process;
    class M,C evidence;
    class G gate;
    class X blocked;
```

## Quality gate

```bash
make eval
```

The gate runs:

- `extraction/seed-v1.json`: deterministic memory kinds and exact evidence.
- `retrieval/seed-v2.json`: current-version lexical retrieval, Unicode, and expected-empty cases.
- `grounded-qa/seed-v1.json`: scripted grounded answers, citation resolution, and abstention.

Expected scores are intentionally perfect because these are regression fixtures. Change behavior by
adding a new dataset version rather than silently weakening an existing expectation.

## Benchmarks

`benchmarks/` records environment-specific watcher, lexical, vector-index, and deterministic
reranker observations. Reproduce them with the matching Make target or script. A benchmark receipt
describes only its revision, fixture, hardware, and command; it is not a portable scale guarantee.

## Model comparison

`real-model/` contains the versioned comparison shape and explicit mock fixtures. Mock execution
requires `--allow-mock`, uses no provider network, and produces `mock_integration` qualification.
Real-model comparison remains outside the current execution scope.

## Pilot material

`pilot/` contains private-study templates only. `pilot-simulation/` contains invented personas and
scripted tasks for credential-free workflow regression. Neither directory contains external pilot
evidence. Follow [`docs/pilot-protocol.md`](../docs/pilot-protocol.md) for a real study.
