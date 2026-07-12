# External pilot artifacts

These version 1 templates support the [external pilot protocol](../../docs/pilot-protocol.md).
They contain no external pilot results. The single question row is synthetic and exists only to
show valid JSONL shape; it MUST be removed before a real dataset is frozen.

Use copies in a private, access-controlled workspace. Do not commit raw questions, answers, source
text, source spans, company names, participant identities, credentials, prompts, or model output.
Only explicitly approved anonymized aggregates may return to this repository.

## Files

- `manifest.v1.template.json`: consent, ownership, study window, retention, and security policy.
- `questions.v1.template.jsonl`: question and relevance-judgment grain, one record per question.
- `attempts.v1.template.csv`: one paired baseline/Proofline observation per eligible question and
  participant, including safe configuration/cost/latency metadata.
- `citations.v1.template.csv`: one human judgment per emitted citation.
- `weekly-usage.v1.template.csv`: one team/week adoption observation.
- `commercial-signals.v1.template.csv`: one dated buyer signal per team.
- `security-platform.v1.template.csv`: team security constraints, deletion checks, findings, and
  supported-platform receipts.
- `gate-review.v1.template.json`: blank decision record with formulas and thresholds fixed in
  advance.

## Conventions

- Timestamps use UTC ISO 8601; study weeks use ISO `YYYY-Www`.
- Durations use integer milliseconds or seconds as named in the header.
- Missing measured values are empty; categorical missingness uses `not_available` only where the
  protocol permits it. Never substitute zero.
- Boolean CSV values are lowercase `true` or `false`.
- IDs are random opaque values. Do not derive participant IDs from email addresses.
- Multi-value CSV fields contain JSON arrays, for example `"[""markdown"",""adr""]"`.
- CSV files are UTF-8 with a header row. JSONL contains one JSON object per line.

## Required enums

| Field | Values |
| --- | --- |
| `intent` | `decision`, `rationale`, `ownership`, `change`, `incident`, `validity` |
| `record_status` | `synthetic_example`, `eligible`, `excluded`, `withdrawn` |
| `completion_status` | `completed`, `insufficient_evidence`, `timeout`, `environment_failure`, `withdrawn` |
| `answer_status` | `grounded`, `insufficient_evidence`, `provider_unavailable`, `not_applicable` |
| `citation_judgment` | `supported`, `unsupported`, `unresolved`, `unjudgeable` |
| `adjudication_status` | `not_needed`, `pending`, `adjudicated` |
| `wtp_status` | `concrete`, `exploratory`, `declined`, `unknown` |
| `finding_severity` | `none`, `low`, `medium`, `high`, `critical` |
| `gate_status` | `open`, `pass`, `fail`, `not_applicable` |

Before analysis, verify at minimum: unique IDs; foreign keys; exactly one eligible question record
per `question_id`; at least 25 eligible real questions and 10 temporal; paired timing coverage;
one judgment for every emitted citation; no synthetic rows in the calculation; and frozen artifact
SHA-256 hashes recorded in the manifest and gate review.
