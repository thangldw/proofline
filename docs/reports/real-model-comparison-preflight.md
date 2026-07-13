# Real-model comparison — preflight foundation

## Technical summary

Proofline can now validate and freeze a local-versus-remote evaluation plan before any paid model
request is sent. No real model was available on 2026-07-13, so this report contains no quality,
latency or cost result and makes no model recommendation.

## No comparative finding exists yet

The current machine had no reachable Ollama endpoint and no configured Qwen or DeepSeek credential.
The preflight path therefore correctly reports explicit blockers instead of substituting synthetic
fixtures. A chart would be misleading with zero real-model observations, so no visualization is
included.

## Scope and metric definitions

The planned comparison uses the checked-in extraction and grounded-QA datasets, identified by
version, provenance and SHA-256 in every receipt. Primary metrics are extraction precision/recall
and grounded-answer citation precision. Guardrails are abstention accuracy, validation failure rate,
per-run latency and estimated cost from provider-reported token counts and declared prices.

The unit of analysis is one evaluation source for extraction and one evaluation question for
grounded QA. Synthetic seed datasets remain regression inputs; running a real model against them is
real-model evidence for that narrow corpus, not external-pilot evidence.

## Methodology and reproducibility

The versioned plan must declare at least one loopback local provider and one non-loopback remote
provider. Each entry records provider ID, model ID, exact model revision, endpoint and input/output
price per million tokens. API keys are resolved only from a named environment variable and never
serialized. Preflight hashes the raw datasets, records the Proofline version and Git revision, locks
the extraction and grounded-answer prompt versions, and checks endpoint health.

## Limitations and robustness

- Model IDs, revisions and prices are operator-declared and must be reconciled with provider records.
- Endpoint health proves availability only; it does not prove structured-output compliance.
- The current receipt type is explicitly `preflight` and cannot satisfy any roadmap quality gate.
- No result should be shared as a model comparison until both providers run the same frozen corpus.

## Recommended next steps

1. Install and pin one Ollama/vLLM model, recording its content digest.
2. Provide one Qwen or DeepSeek API key through the manifest-named environment variable.
3. Implement the token-spending runner using the production extraction and grounded-answer paths.
4. Validate aggregate metrics against per-source/per-question rows before recommending a default.

## Further questions

- Which remote model and price region should be treated as the first budget baseline?
- Which local quantization and hardware profile should define the reproducible local comparison?
