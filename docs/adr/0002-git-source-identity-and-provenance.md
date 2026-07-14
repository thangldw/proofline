# ADR 0002: Local Git source identity

Status: accepted and implemented.

An explicitly registered local repository is read at a resolved commit. Git file identity combines
repository identity, commit SHA, and tracked path; commit metadata uses the repository identity and
commit SHA. Content at an imported commit is immutable even after the working tree changes.

```mermaid
flowchart LR
    R["Repository"] --> C["Commit SHA"]
    C --> P["Tracked path"]
    P --> V["Immutable source version"]
    V --> E["Exact line evidence"]

    classDef source fill:#FFF4C2,stroke:#7A6F45,color:#172B4D;
    classDef identity fill:#DDEBFF,stroke:#5B7DB1,color:#172B4D;
    classDef evidence fill:#DDF7EA,stroke:#4C8B6B,color:#172B4D;
    class R source;
    class C,P identity;
    class V,E evidence;
```

Only tracked text files and bounded commit metadata enter the index. Network clone, OAuth, webhook,
pull-request automation, and write-back are outside this decision. Re-scan is idempotent and source
deletion cascades through all derived records.
