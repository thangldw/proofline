# Provider configuration

Proofline runs with model providers disabled by default. Use the Settings screen or
`PUT /api/v1/model/configuration` to configure generation and embedding independently.

Proofline defaults to writing `.proofline/providers.json` atomically with owner-only permissions.
Set `PROOFLINE_PROVIDER_CONFIG_PATH` to choose another local path. Environment variables retain
precedence over local storage, which keeps container and managed deployments declarative.

Desktop wrappers should enable the operating-system credential store before startup:

```bash
export PROOFLINE_SECRET_STORE=os_keyring
proofline serve --port 0 --data-dir "$HOME/Library/Application Support/Proofline"
```

The `os_keyring` mode uses macOS Keychain on macOS and Windows Credential Locker on Windows through
the Python `keyring` backend. Non-secret provider settings remain in `providers.json`; generation
and embedding API keys do not. The Settings screen reports which storage mode is active and lets
the user replace or explicitly remove either saved key. On the first successful save in keyring
mode, legacy keys are moved out of `providers.json`. If provider validation fails, both the file
and keyring changes are rolled back. Startup fails explicitly when keyring mode is selected but no
usable OS backend is available. Use `PROOFLINE_SECRET_STORE=file` (the default) only when the
owner-only local file behavior is intended.

Supported generation profiles are `qwen`, `deepseek`, `ollama`, `vllm`, and
`openai_compatible`. Embedding profiles are `ollama`, `vllm`, and `openai_compatible`. Qwen,
DeepSeek, and other non-loopback endpoints require `allow_remote_ai=true`. API keys are accepted
on write, are never returned on read, and are not included in model-run diagnostics, portable
exports, SQLite backups or platform receipts.

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
