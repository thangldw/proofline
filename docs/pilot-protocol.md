# External Pilot Protocol

**Protocol version:** 1.0

**Status:** Ready for evidence collection; no pilot results are recorded here

**Decision:** Whether Proofline has enough evidence to continue toward a public beta

This protocol turns the open gates in the [90-day roadmap](./roadmap-90-days.md) into a
repeatable external study. Synthetic fixtures may test the collection format, but they never count
as pilot evidence.

## 1. Scope and minimum sample

Recruit up to five independent engineering teams or equivalent design partners. The decision set
MUST contain at least 25 permissioned, real engineering-context questions from consented
participants. At least 10 questions MUST be temporal: answering them requires identifying a
decision, assumption, constraint, or alternative that changed, expired, or was superseded.

Each question receives a stable opaque `question_id`. Teams and participants receive pseudonymous
IDs; names, company names, repository names, issue numbers, URLs, source excerpts, and customer
identifiers MUST NOT enter the committed pilot artifacts.

The pilot owner records the predeclared study window, participating pseudonymous teams, owners,
approved providers, retention period, and security constraints in
`evals/pilot/manifest.v1.template.json` copied to a private pilot workspace.

## 2. Roles and approval

The manifest MUST name one person for each role:

- **pilot owner:** recruitment, consent, cadence, and protocol deviations;
- **evaluation owner:** question eligibility, judgments, metric calculation, and frozen exports;
- **security owner:** data classification, provider egress, retention, incidents, and deletion;
- **product decision owner:** signs the final continue, narrow, pause, or stop decision.

One person may hold multiple roles, but no evaluator should judge an answer they authored. A second
reviewer resolves disputed citation or usefulness judgments. All deviations are recorded before
metrics are calculated.

## 3. Consent, privacy, and sanitization

Before ingestion or observation, obtain written consent covering:

1. the question and source families that may be processed;
2. whether local-only or named remote model providers are allowed;
3. what telemetry is collected and what is explicitly excluded;
4. retention and deletion dates;
5. whether sanitized question-level data or only aggregate metrics may be published; and
6. withdrawal and incident contacts.

Raw pilot data stays outside the public repository in an access-controlled location. Use a random
team ID or a salted HMAC; keep the identity map separately. Never publish the salt or mapping.
Participant IDs are unique within a team and MUST NOT be email hashes.

Sanitization removes or replaces:

- organization, person, customer, host, repository, branch, ticket, and service names;
- credentials, secrets, personal data, confidential code, URLs, and verbatim source spans;
- rare combinations that could re-identify a team; and
- model prompts and model output beyond the separately approved, sanitized answer judgment.

Keep only opaque evidence IDs and judgments in the shared artifact. Do not publish team-level cuts
when fewer than three teams contribute to a group. A withdrawal removes the team's raw records and
recomputes all aggregates; previous frozen reports remain marked withdrawn and MUST NOT be reused.

## 4. Security constraints and stop conditions

For every team, record data classification, allowed roots/source families, allowed providers,
egress mode, retention end, deletion verification date, and unresolved findings. The most
restrictive team constraint controls that team's run.

Stop collection for an affected team immediately on suspected unauthorized egress, credential or
source-content logging, cross-team data exposure, incorrect deletion, evidence resolving to the
wrong immutable source version, or a critical vulnerability. Quarantine artifacts, notify the
security owner, preserve only approved incident evidence, and resume only after written approval.

A critical security or deletion-integrity defect keeps the release gate open even if product
metrics pass.

## 5. Question and relevance preparation

Collect questions before demonstrating Proofline. A question is eligible when it reflects a real
task and an authorized reviewer can identify the relevant source evidence. Record:

- intent: decision, rationale, ownership, change, incident, or validity;
- whether temporal reasoning is required;
- sanitized source-family labels;
- opaque relevant-evidence references and the reviewer who established them; and
- eligibility or exclusion reason.

Freeze the eligible question set and its SHA-256 artifact hashes before scoring. Added or corrected
questions require a new dataset version; never overwrite a frozen version.

## 6. Baseline and Proofline procedure

Use the same question, participant role, authorized source set, and completion definition for both
conditions. The baseline is the team's current normal tools; record which tools were used. Measure
baseline before exposing that question's Proofline result, preferably at least 24 hours earlier.
If order differs, record it and treat learning carryover as a limitation.

Start the timer when the participant reads the question. Stop when they either:

- provide an answer they consider actionable and point to its supporting source; or
- declare that evidence is insufficient.

Predeclare a timeout, recommended at 1,800 seconds. A timeout is recorded at the cap, not discarded.
Record seconds, completion status, number of sources opened, and confidence. Repeat the procedure
with Proofline after the approved sources are indexed. Exclude a pair only for a predeclared reason
such as withdrawn consent or an environment failure unrelated to the product; preserve the reason.

## 7. Human judgments

### Citation judgment

Every emitted citation receives one row in `citations.v1.template.csv`. The reviewer checks that:

- the citation resolves to the immutable source version and exact span;
- the span supports the statement attributed to it; and
- the citation belongs to the authorized source set.

Use `supported`, `unsupported`, `unresolved`, or `unjudgeable`. For the gate, every state except
`supported` counts as incorrect. A response with no emitted citations contributes zero citation
rows and cannot be rated useful if it makes evidence-dependent claims.

### Useful-answer judgment

After the task, the participant rates usefulness from 1 to 5:

1. unusable;
2. mostly wrong or materially incomplete;
3. partially useful but requires substantial verification;
4. useful with minor verification;
5. directly actionable.

An answer is useful only when the rating is 4 or 5, the participant completed the task, and no
statement has an unresolved or unsupported citation. `insufficient_evidence` may be useful when the
reviewer confirms that abstention was correct.

Judges record their own pseudonymous ID. Disagreements are retained; the adjudicated value and
adjudicator are separate fields, not silent replacements.

## 8. Model, retrieval, cost, and latency receipt

Each Proofline attempt records a configuration receipt without secrets or payloads:

- Proofline revision and dataset version;
- generation and embedding provider/model IDs;
- prompt/template and retrieval configuration versions;
- local or remote execution and egress policy;
- answer status and model-run IDs;
- end-to-end latency and provider latency when available;
- input/output token counts when available; and
- currency, estimated cost, and estimation method.

Missing provider usage is recorded as `not_available`, never estimated as zero. Cost comparisons
must use one declared currency and include the pricing date or a local-compute estimation method.

## 9. Weekly adoption and commercial signal

A **qualifying team-week** requires at least one non-demo workflow completed by a consented team
member on a real eligible question. Record the ISO week, active participant count, qualifying
workflow count, useful workflow count, and evidence source. Do not use number of notes or tokens as
adoption.

A team counts as **weekly active** for the release gate when it has a qualifying team-week in at
least three of the final four study weeks. If the study is shorter than four weeks, the weekly-use
gate remains open.

Willingness to pay is concrete only when a named buyer role confirms all of: a defined managed or
team capability, a price or budget range, and a dated next step such as a paid pilot, procurement
review, or contract discussion. General enthusiasm or an unpriced survey answer does not count.

## 10. Metric definitions and formulas

Calculate from one frozen dataset version. Report numerator, denominator, exclusions, missingness,
team coverage, and a bootstrap 95% confidence interval where the sample permits. Do not mix
synthetic and external rows.

| Metric | Formula | Gate |
| --- | --- | --- |
| Citation precision | `supported citations / all emitted citations` | `>= 0.90` |
| Useful-answer rate | `useful eligible Proofline attempts / all eligible judged Proofline attempts` | `>= 0.65` |
| Median time improvement | `1 - median(Proofline seconds) / median(baseline seconds)` on complete eligible pairs, with timeouts capped | `>= 0.50` |
| Weekly team usage | teams qualifying in at least 3 of final 4 weeks | `>= 3 of 5`; denominator and missing teams reported |
| Concrete willingness to pay | distinct teams meeting every commercial-signal condition | `>= 2` |

Additional hard gates:

- at least 25 eligible real questions and at least 10 eligible temporal questions;
- every emitted citation has a judgment and resolves to authorized evidence;
- no unresolved critical security or deletion-integrity defect; and
- the declared supported setup has a successful, timestamped platform receipt.

Do not substitute mean time savings for the median formula, question count for team adoption, or
synthetic regression scores for external judgments.

## 11. Decision rule

The decision owner signs one outcome:

- **Continue:** every product, adoption, commercial, security, corpus, and platform gate passes.
- **Narrow:** trust/security gates pass, but one or more value gates miss; state the failed
  hypothesis and narrow source family, ontology, or user segment before adding features.
- **Pause:** evidence is incomplete, consent/quality is insufficient, or confidence is too low;
  name the exact evidence needed to resume.
- **Stop:** a core trust constraint is infeasible or repeated real use shows no actionable value.

No gate may be marked passed from anecdotes. The final artifact includes dataset hashes, protocol
version, calculation date, deviations, missing data, owner signatures, and links to private source
records where authorized.

## 12. Artifact workflow

1. Copy the versioned templates under `evals/pilot/` into an access-controlled pilot workspace.
2. Fill the manifest and obtain consent/security approval before collecting questions.
3. Freeze question and relevance records, record their hashes, then collect paired attempts.
4. Add citation judgments, weekly activity, commercial signals, and security/platform receipts.
5. Validate identifiers, counts, allowed enums, required fields, and referential integrity.
6. Freeze a read-only export, compute hashes, calculate metrics, and obtain owner sign-off.
7. Commit only synthetic-safe templates or explicitly approved anonymized aggregates.

Templates contain no pilot evidence and MUST remain clearly labeled as blank or synthetic examples.
