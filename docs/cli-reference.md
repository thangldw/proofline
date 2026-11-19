# CLI reference

## English

Run `proofline COMMAND --help` for the exact option schema. Commands return zero on success and non-zero on invalid input, failed verification, policy failure, or runtime error. Verification commands do not mutate their inputs.

| Group | Commands | Contract |
|---|---|---|
| Local app | `serve`, `launch`, `seed` | Run local API/UI or index the bundled example. `serve` accepts host, port, data directory, lifecycle files, web directory, and API-only mode. |
| Evaluation | `eval`, `eval-grounded`, `eval-extraction`, `eval-real-model-preflight`, `eval-real-model`, `benchmark` | Run versioned evaluation or benchmark plans; real-model commands require explicit provider configuration. |
| Indexing | `embed` | Incrementally embed current source chunks using configured providers. |
| Portable snapshot | `export`, `verify-export`, `import` | Export, verify, restore, or explicitly merge portable JSON state. |
| Evidence package | `export-package`, `verify-package`, `explain`, `diff` | Export or independently verify a DEP; explain content-free provenance; verify both packages before diffing. |
| Review receipt | `export-review-receipt`, `verify-review-receipt` | Bind a persisted review to a verified DEP and verify the receipt offline. |
| Attestation | `generate-attestation-key`, `attest`, `verify-attestation` | Generate a local Ed25519 keypair, sign exact verified subjects, or verify against a trusted public key and an optional `--revocations` list. |
| Recovery | `backup`, `verify-backup`, `restore-backup`, `verify-integrity` | Create/verify SQLite backup, atomically restore with rollback output, or check live provenance. |
| Decision lookup | `blame` | `proofline blame docs/adr.md:42` lists approved decisions anchored at that file or line, with anchor state and current line span. |
| Decision lookup | `why` | `proofline why "why SQLite?"` returns matching approved decisions with citation and a warning when the citation is stale. Deterministic term matching; no generated prose. |
| Decision trend | `snapshot-health`, `health-trend` | `snapshot-health` records counts only (approved, stale, moved, changed, ambiguous, deleted; never text) per workspace; run it on a schedule. `health-trend` prints the series as text bars, JSON or a Markdown table. |
| Workspace check | `doctor` | Read-only overview: migrations current, integrity verified, optional policy file valid (`--policy`), reviews open longer than the policy allows, age of the last snapshot. Exit 1 only on a failed check; warnings do not fail. |
| Decision import | `import-adr` | `import-adr adr/ --output-dir imported/` converts Nygard/MADR-style Markdown ADRs (title, status, Decision and Context/Rationale sections) into `Decision:`/`Rationale:`/`Status:` files, then run `proofline sync imported/`. Files with no decision section are listed as skipped; status words map to accepted, candidate, rejected or obsolete, and unknown ones become candidate. Never writes to the database; refuses to overwrite without `--force`. |
| Decision export | `export-adr` | `export-adr --output-dir adr/` writes one numbered Markdown ADR per approved decision (status, source line span, rationale, quoted evidence, citation health). Refuses to overwrite without `--force`. |
| Report | `report` | `report --output health.html` writes a self-contained page (no external resources, light and dark) with the stale-percent trend, stale citations, reviews due within 30 days and possible conflicts; `--format markdown` prints the same as Markdown. `--no-titles` withholds decision titles and source names. Read-only. |
| Shell | `completion` | `completion bash|zsh|fish` prints a completion script generated from the live command tree, so it never drifts: `eval "$(proofline completion bash)"`, or save it to your shell's completion directory. |
| Graph | `graph` | `graph` prints the approved-decision relation graph as Mermaid (`--format dot` for Graphviz). Stale decisions are coloured, possible conflicts are dashed edges (`--no-conflicts` to omit), unlinked decisions are skipped unless `--include-isolated`, and `--no-titles` labels nodes with short ids. Labels are escaped. |
| Policy schema | `policy-schema` | Prints the JSON Schema for `proofline.toml`, generated from the loader's own constants; a copy is committed at `spec/decision-policy/v1/schema.json` for editor completion and validation. |
| Notification | `notify` | `notify --webhook URL` POSTs a content-free JSON alert (decision ids, states, review dates and counts; never titles or text) for reviews overdue or due within `--warn-within` days (default 7). `--style slack` sends `{"text": ...}`. Sends nothing when nothing is due unless `--always`. https only, or http to a loopback host; no redirects are followed, 10 s timeout, exit 2 on delivery failure. Run it from the weekly routine or cron. |
| Git hook | `hook install`, `hook uninstall` | `hook install` writes a pre-commit hook (honours `core.hooksPath` and worktrees) that runs `check-code-refs` on staged files; `--with-decisions` also runs `sync` and `check-decisions` on the working tree. The hook skips quietly when `proofline` is not on `PATH`. A hook Proofline did not write is never replaced or removed without `--force`. |
| Code links | `check-code-refs` | Scans files for `proofline-decision: <id or 8+ char prefix>` and exits 1 for references that are missing, ambiguous, unapproved or stale. Skips `.git`, `node_modules`, `.venv`. |
| Conflict candidates | `find-conflicts` | Lists approved decision pairs with overlapping title words but different statements and no relation. Candidates for a person to judge, not verdicts. |
| Decision repair | `rebind` | `rebind` lists pending reviews; `rebind <id>` shows a diff of cited vs current text; `rebind <id> --apply --reason "..."` re-anchors the decision. Ambiguous or candidate-less reviews are refused. |
| Decision review dates | `check-expiry` | Exit 1 when an approved decision has a `Review by: YYYY-MM-DD` line in its cited text that is in the past (`--as-of`, `--warn-within DAYS`, `--format json`). `Review every: N days/weeks/months/years` repeats from the date the cited version was recorded, so re-anchoring with `rebind` restarts the cycle. Changing the date is a reviewed edit: the citation changes, then `rebind` accepts it. |
| Decision links | `suggest-links` | `suggest-links <id>` lists approved decisions with overlapping title and statement words that have no relation yet, with the relation kinds to consider. Suggestions only; nothing is created. |
| Decision health | `check-decisions`, `refresh-reviews`, `check-impacts` | Run read-only stale/impact CI checks or persist the current review ledger. |

`check-decisions --explain` prints, for each finding, why it fires, whether it blocks under the policy, and the command that fixes it. Directory overrides in `proofline.toml` set a different blocking list per path, for example `overrides = [{path = "notes", fail_on = []}, {path = "docs/adr", fail_on = ["moved", "changed"]}]` under `[decision_health]`; the longest matching directory wins and an override changes the policy hash.

| Headless sync | `sync` | Index a document folder without a server, under a stable `--uri-root`, so CI can reuse a committed snapshot. See [PR gate](pr-gate.md). |
| Local MCP | `mcp` | Serve read-only decision checks to a local MCP client over stdio; titles and evidence excerpts are withheld unless `--include-titles` / `--include-excerpts`. See [MCP](mcp.md). |
| Demo | `demo stale-decision` | Run the self-contained stale-citation story; output directory reuse requires `--force`. |

Common verification examples:

```bash
proofline verify-package evidence.json
proofline verify-review-receipt decision-review.json
proofline verify-attestation envelope.json --public-key trusted.pem --package evidence.json
proofline check-decisions --policy proofline.toml --format sarif
proofline check-impacts --format sarif
```

`check-decisions --format json` emits only identifiers, hashes, spans, anchor state, and
counts. A policy-blocking finding still writes the JSON document and exits with status 1:

```json
{"blocking_count":1,"finding_count":1,"findings":[{"candidate_end_line":null,"candidate_end_offset":null,"candidate_start_line":null,"candidate_start_offset":null,"cited_content_sha256":"<sha256>","cited_source_version_id":"<version-id>","current_content_sha256":"<sha256>","current_source_version_id":"<version-id>","decision_id":"<decision-id>","end_line":48,"end_offset":512,"evidence_id":"<evidence-id>","quote_sha256":"<sha256>","reason":"changed","source_id":"<source-id>","start_line":42,"start_offset":384}],"policy_sha256":"<sha256>","valid":false}
```

Decision titles, source titles, source URIs, and source text are excluded from this JSON contract.

`verify-package`, `verify-review-receipt`, `verify-attestation`, `verify-backup`, and `verify-integrity` fail closed. Safe errors identify the failed contract without returning confidential source text.

## Tiếng Việt

Chạy `proofline COMMAND --help` để xem option schema chính xác. Command trả zero khi thành công và non-zero khi input sai, verification fail, policy fail hoặc runtime error. Verification command không mutate input.

| Nhóm | Command | Contract |
|---|---|---|
| Local app | `serve`, `launch`, `seed` | Chạy API/UI local hoặc index bundled example. `serve` nhận host, port, data directory, lifecycle file, web directory và API-only mode. |
| Evaluation | `eval`, `eval-grounded`, `eval-extraction`, `eval-real-model-preflight`, `eval-real-model`, `benchmark` | Chạy versioned evaluation hoặc benchmark plan; real-model command cần provider configuration explicit. |
| Indexing | `embed` | Incremental embed current source chunk bằng provider đã cấu hình. |
| Portable snapshot | `export`, `verify-export`, `import` | Export, verify, restore hoặc explicit merge portable JSON state. |
| Evidence package | `export-package`, `verify-package`, `explain`, `diff` | Export hoặc verify DEP độc lập; explain provenance không trả content; verify cả hai package trước diff. |
| Review receipt | `export-review-receipt`, `verify-review-receipt` | Gắn persisted review với DEP đã verify và verify receipt offline. |
| Attestation | `generate-attestation-key`, `attest`, `verify-attestation` | Generate keypair Ed25519 local, sign exact verified subject hoặc verify với trusted public key. |
| Recovery | `backup`, `verify-backup`, `restore-backup`, `verify-integrity` | Tạo/verify SQLite backup, atomic restore có rollback output hoặc check live provenance. |
| Decision health | `check-decisions`, `refresh-reviews`, `check-impacts` | Chạy stale/impact CI check read-only hoặc persist review ledger hiện tại. |
| Demo | `demo stale-decision` | Chạy stale-citation story self-contained; reuse output directory cần `--force`. |

Ví dụ verification phổ biến:

```bash
proofline verify-package evidence.json
proofline verify-review-receipt decision-review.json
proofline verify-attestation envelope.json --public-key trusted.pem --package evidence.json
proofline check-decisions --policy proofline.toml --format sarif
proofline check-impacts --format sarif
```

`check-decisions --format json` chỉ xuất identifier, hash, span, anchor state và count.
Khi finding bị policy chặn, command vẫn ghi JSON document và trả exit status 1:

```json
{"blocking_count":1,"finding_count":1,"findings":[{"candidate_end_line":null,"candidate_end_offset":null,"candidate_start_line":null,"candidate_start_offset":null,"cited_content_sha256":"<sha256>","cited_source_version_id":"<version-id>","current_content_sha256":"<sha256>","current_source_version_id":"<version-id>","decision_id":"<decision-id>","end_line":48,"end_offset":512,"evidence_id":"<evidence-id>","quote_sha256":"<sha256>","reason":"changed","source_id":"<source-id>","start_line":42,"start_offset":384}],"policy_sha256":"<sha256>","valid":false}
```

Contract JSON này loại bỏ decision title, source title, source URI và source text.

`verify-package`, `verify-review-receipt`, `verify-attestation`, `verify-backup` và `verify-integrity` fail closed. Safe error chỉ ra contract bị fail mà không trả confidential source text.

## 日本語

正確な option schema は `proofline COMMAND --help` で確認します。Command は成功時 zero、invalid input、verification failure、policy failure、runtime error では non-zero を返します。Verification command は入力を変更しません。

| Group | Command | Contract |
|---|---|---|
| Local app | `serve`, `launch`, `seed` | Local API/UI を実行、または bundled example を index します。`serve` は host、port、data directory、lifecycle file、web directory、API-only mode を受け取ります。 |
| Evaluation | `eval`, `eval-grounded`, `eval-extraction`, `eval-real-model-preflight`, `eval-real-model`, `benchmark` | Versioned evaluation または benchmark plan を実行します。Real-model command には explicit provider configuration が必要です。 |
| Indexing | `embed` | 設定済み provider で current source chunk を incremental embed します。 |
| Portable snapshot | `export`, `verify-export`, `import` | Portable JSON state を export、verify、restore、または explicit merge します。 |
| Evidence package | `export-package`, `verify-package`, `explain`, `diff` | DEP を export/independent verify し、content-free provenance を explain し、両 package を verify 後に diff します。 |
| Review receipt | `export-review-receipt`, `verify-review-receipt` | Persisted review を verified DEP に結び付け、receipt を offline verify します。 |
| Attestation | `generate-attestation-key`, `attest`, `verify-attestation` | Local Ed25519 keypair の生成、exact verified subject の署名、trusted public key による検証を行います。 |
| Recovery | `backup`, `verify-backup`, `restore-backup`, `verify-integrity` | SQLite backup の作成/検証、rollback output 付き atomic restore、live provenance check を行います。 |
| Decision health | `check-decisions`, `refresh-reviews`, `check-impacts` | Read-only stale/impact CI check、または current review ledger の persist を行います。 |
| Demo | `demo stale-decision` | Self-contained stale-citation story を実行します。Output directory の再利用には `--force` が必要です。 |

一般的な verification 例：

```bash
proofline verify-package evidence.json
proofline verify-review-receipt decision-review.json
proofline verify-attestation envelope.json --public-key trusted.pem --package evidence.json
proofline check-decisions --policy proofline.toml --format sarif
proofline check-impacts --format sarif
```

`check-decisions --format json` は identifier、hash、span、anchor state、count のみを出力します。
Policy-blocking finding がある場合も JSON document を出力し、exit status 1 を返します：

```json
{"blocking_count":1,"finding_count":1,"findings":[{"candidate_end_line":null,"candidate_end_offset":null,"candidate_start_line":null,"candidate_start_offset":null,"cited_content_sha256":"<sha256>","cited_source_version_id":"<version-id>","current_content_sha256":"<sha256>","current_source_version_id":"<version-id>","decision_id":"<decision-id>","end_line":48,"end_offset":512,"evidence_id":"<evidence-id>","quote_sha256":"<sha256>","reason":"changed","source_id":"<source-id>","start_line":42,"start_offset":384}],"policy_sha256":"<sha256>","valid":false}
```

Decision title、source title、source URI、source text はこの JSON contract に含まれません。

`verify-package`、`verify-review-receipt`、`verify-attestation`、`verify-backup`、`verify-integrity` は fail closed します。Safe error は confidential source text を返さず、失敗 contract を示します。
