# Provider configuration

Proofline runs with model providers disabled by default. Use the Settings screen or
`PUT /api/v1/model/configuration` to configure generation and embedding independently.

The UI writes `.proofline/providers.json` atomically with owner-only permissions. Set
`PROOFLINE_PROVIDER_CONFIG_PATH` to choose another local path. Environment variables retain
precedence over the file, which keeps container and managed deployments declarative.

Supported generation profiles are `qwen`, `deepseek`, `ollama`, `vllm`, and
`openai_compatible`. Embedding profiles are `ollama`, `vllm`, and `openai_compatible`. Qwen,
DeepSeek, and other non-loopback endpoints require `allow_remote_ai=true`. API keys are accepted
on write, are never returned on read, and are not included in model-run diagnostics.

Capability checks:

```text
GET /api/v1/model/provider?check_health=true
GET /api/v1/model/embedding-provider?check_health=true
GET /api/v1/model/reranking-provider
```

Reranking currently reports `disabled`. A failed generation or embedding provider does not stop
deterministic ingestion or lexical retrieval.

Transient network/timeouts, `408`, `409`, `425`, `429`, and selected `5xx` responses receive at
most three attempts. Other failures are not retried. Exhaustion creates a `dead_letter` run.
Retry an extraction run with its original immutable source:

```text
POST /api/v1/model/runs/{run_id}/retry
{"source_id":"...","operation":"extract_memories"}
```

The configured provider ID and model ID must exactly match the failed run. Proofline never falls
back to another provider.
