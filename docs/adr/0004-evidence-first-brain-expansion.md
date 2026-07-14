# ADR 0004: Evidence-first personal, learning, and action memory

Status: accepted and implemented for a single local user.

Notes create immutable source revisions; hashtags and wiki-links use deterministic offsets;
backlinks identify the exact originating revision. Study cards derive from explicit source patterns
and keep append-only review history. Action proposals remain grounded candidates with exact
citations and human accept/reject audit.

```mermaid
flowchart LR
    R(("Evidence-first memory"))
    R --> P["Personal"]
    R --> L["Learning"]
    R --> A["Action"]
    R -. blocked .-> T["Shared"]
    P --> P1["Notes · revisions · backlinks"]
    L --> L1["Study cards · review history"]
    A --> A1["Proposal · human decision"]
    T --> T1["Auth · RBAC · permissions"]

    classDef root fill:#DDEBFF,stroke:#5B7DB1,color:#172B4D;
    classDef branch fill:#FFF4C2,stroke:#7A6F45,color:#172B4D;
    classDef detail fill:#DDF7EA,stroke:#4C8B6B,color:#172B4D;
    classDef blocked fill:#FFE4E1,stroke:#A35D57,color:#172B4D;
    class R root;
    class P,L,A branch;
    class P1,L1,A1 detail;
    class T,T1 blocked;
```

Team Brain is not an extension of this local decision. It requires authentication, RBAC,
organization audit, and permission-aware retrieval before shared data or collaboration can begin.
