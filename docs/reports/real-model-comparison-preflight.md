# Real-model comparison — mock integration validation

## Technical summary

Proofline can now validate, freeze and execute a local-versus-remote evaluation plan through the
production extraction and grounded-QA paths. A deterministic injected transport and fake API key
validated the runner on 2026-07-13. No real model was available, so this report makes no model
recommendation.

## Perfect mock scores validate wiring, not model quality

Each mock profile produced one matched extraction from one expected memory and no extraction from
one negative source: precision and recall were therefore `1 / 1 = 100%`, while negative-source
accuracy was `1 / 1 = 100%`. The grounded fixture resolved one relevant citation from one emitted
citation and correctly abstained on one of one insufficient-evidence query, also yielding 100%.

Both mock profiles use the same deterministic behavior, so a comparison chart would imply a model
difference that does not exist. No visualization is included. These exact 100% values are expected
for the fixture and are not evidence of general model quality.

## Scope and metric definitions

The comparison uses versioned extraction and grounded-QA datasets, identified by
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

The mock calculation spot-check used three provider calls per profile: two extraction sources and
one grounded question requiring generation. At 11 prompt and 7 completion tokens per mock response,
the aggregate is 33 prompt and 21 completion tokens. With declared remote prices of `$0.10` and
`$0.20` per million tokens, the independently recomputed estimate is
`(33 × 0.10 + 21 × 0.20) / 1,000,000 = $0.0000075`.

## Limitations and robustness

- Model IDs, revisions and prices are operator-declared and must be reconciled with provider records.
- Mock endpoint health and structured output prove test transport behavior only.
- Mock receipts are explicitly `mock_integration` and cannot satisfy any roadmap quality gate.
- No result should be shared as a model comparison until both providers run the same frozen corpus.

## Recommended next steps

1. Install and pin one Ollama/vLLM model, recording its content digest.
2. Provide one Qwen or DeepSeek API key through the manifest-named environment variable.
3. Run the implemented comparison command against the frozen real providers and corpus.
4. Validate aggregate metrics against per-source/per-question rows before recommending a default.

## Validation assessment

**Ready to share as mock integration evidence only.** Numerators, denominators, token totals and the
cost formula were independently spot-checked. **Needs real-model evidence before any model-selection
decision.** The missing model endpoints and credentials remain hard blockers, not caveats.

## Further questions

- Which remote model and price region should be treated as the first budget baseline?
- Which local quantization and hardware profile should define the reproducible local comparison?
