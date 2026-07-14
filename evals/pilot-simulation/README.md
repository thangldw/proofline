# Synthetic pilot simulation

`engineering-context-v1.json` contains invented sources and scripted expectations. It exercises
production migrations, ingestion, retrieval, bounded evidence, grounded-answer validation, and
exact citation resolution without credentials or network access.

```mermaid
flowchart LR
    S["Invented sources"] --> P["Production local path"]
    E["Scripted expectations"] --> P
    P --> R["Synthetic receipt"]
    R --> N["Never pilot evidence"]

    classDef fixture fill:#FFF4C2,stroke:#7A6F45,color:#172B4D;
    classDef process fill:#DDEBFF,stroke:#5B7DB1,color:#172B4D;
    classDef result fill:#DDF7EA,stroke:#4C8B6B,color:#172B4D;
    classDef warning fill:#FFE4E1,stroke:#A35D57,color:#172B4D;
    class S,E fixture;
    class P process;
    class R result;
    class N warning;
```

```bash
make simulate-pilot
```

The result is labelled `synthetic_pilot_simulation`. Completion means scripted status, statement
kinds, expected sources, and exact citations matched. Its source-inspection baseline is not human
time, its citation score is not human entailment judgment, and its latency is local-only.

Do not count simulation output toward real questions, useful-answer rate, weekly adoption,
willingness-to-pay, external citation precision, or production performance.
