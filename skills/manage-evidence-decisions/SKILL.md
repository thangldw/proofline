---
name: manage-evidence-decisions
description: Review, explain, verify, or compare evidence-backed engineering decisions with Proofline. Use for ADRs, exact source citations, provenance review, stale-decision checks, Decision Evidence Packages, review receipts, and signed attestations.
---

# Manage evidence-backed decisions

## English

### Runtime boundary

Resolve all bundled paths relative to this `SKILL.md`. For Decision Evidence Packages and review receipts, use Python 3.11+ with `scripts/proofline_package.py`; it is standard-library-only and does not require a separate checkout, database, network, account, or model credential. Run `python3 scripts/proofline_package.py --help` before an unfamiliar operation.

Signed attestations require an installed Proofline 2.0.1 runtime. The bundled verifier does not verify Ed25519. Run `proofline verify-attestation` only when the user supplies the exact envelope, package, trusted public key, and any bound review receipt. A public key shipped beside an untrusted artifact is not independently trusted.

### Workflow

1. Resolve the requested decision/package and exact local scope.
2. For a new decision, identify source, immutable version, exact span, statement, alternatives, and rationale; do not invent missing evidence.
3. Select the narrowest read-only command from [commands](references/commands.md).
4. Verify before explain or diff. Preserve inputs and return stable errors directly.
5. Separate source evidence, engineering judgment, historical decision status, and current review state.
6. Report decision, evidence locations, source versions, freshness, integrity, limitations, and next action/review trigger.

### Guardrails

- A citation does not prove that a decision is correct. A hash proves integrity, not authenticity.
- Never rewrite cited source content to make stale evidence appear current.
- Never request, display, copy, or persist a private key. A valid signature proves matching key control relative to the trusted public key, not identity or trusted time.
- Verification, explanation, comparison, and receipt verification are read-only. Do not overwrite ADRs, packages, reports, or backups without explicit approval.
- Do not enable a model/embedding provider or transfer source content without explicit configuration and authorization.
- Do not expose source content, local paths, credentials, or packages beyond the selected audience. Bundled explanations return hashes and span locations, not quotes.

## Tiếng Việt

### Runtime boundary

Resolve mọi bundled path relative với `SKILL.md` này. Với Decision Evidence Package và review receipt, dùng Python 3.11+ cùng `scripts/proofline_package.py`; script chỉ dùng standard library và không cần checkout riêng, database, network, account hoặc model credential. Chạy `python3 scripts/proofline_package.py --help` trước operation chưa quen.

Signed attestation cần runtime Proofline 2.0.1 đã cài. Bundled verifier không verify Ed25519. Chỉ chạy `proofline verify-attestation` khi người dùng cung cấp exact envelope, package, trusted public key và review receipt được bind nếu có. Public key đi cùng untrusted artifact không phải independently trusted.

### Workflow

1. Resolve decision/package được yêu cầu và exact local scope.
2. Với decision mới, xác định source, immutable version, exact span, statement, alternative và rationale; không invent evidence thiếu.
3. Chọn read-only command hẹp nhất từ [commands](references/commands.md).
4. Verify trước explain hoặc diff. Giữ nguyên input và trả stable error trực tiếp.
5. Tách source evidence, engineering judgment, historical decision status và current review state.
6. Báo decision, evidence location, source version, freshness, integrity, limitation và next action/review trigger.

### Guardrail

- Citation không chứng minh decision đúng. Hash chứng minh integrity, không phải authenticity.
- Không rewrite cited source content để stale evidence có vẻ current.
- Không request, display, copy hoặc persist private key. Signature hợp lệ chứng minh matching key control tương ứng trusted public key, không phải identity hoặc trusted time.
- Verification, explanation, comparison và receipt verification là read-only. Không overwrite ADR, package, report hoặc backup nếu chưa explicit approval.
- Không enable model/embedding provider hoặc transfer source content nếu chưa explicit configuration và authorization.
- Không expose source content, local path, credential hoặc package ngoài audience được chọn. Bundled explanation trả hash và span location, không trả quote.

## 日本語

### Runtime boundary

全 bundled path はこの `SKILL.md` からの相対 path として解決します。Decision Evidence Package と review receipt には Python 3.11+ と `scripts/proofline_package.py` を使います。Standard-library-only で、別 checkout、database、network、account、model credential は不要です。不慣れな operation の前に `python3 scripts/proofline_package.py --help` を実行します。

Signed attestation には installed Proofline 2.0.1 runtime が必要です。Bundled verifier は Ed25519 を検証しません。User が exact envelope、package、trusted public key、bind された review receipt を提供した場合だけ `proofline verify-attestation` を実行します。Untrusted artifact の隣にある public key は independently trusted ではありません。

### Workflow

1. Requested decision/package と exact local scope を解決します。
2. 新 decision では source、immutable version、exact span、statement、alternative、rationale を特定し、missing evidence を作りません。
3. [Commands](references/commands.md) から最小の read-only command を選びます。
4. Explain/diff 前に verify し、input を保持し stable error を直接返します。
5. Source evidence、engineering judgment、historical decision status、current review state を分離します。
6. Decision、evidence location、source version、freshness、integrity、limitation、next action/review trigger を報告します。

### Guardrail

- Citation は decision の正しさを証明しません。Hash が証明するのは integrity で、authenticity ではありません。
- Stale evidence を current に見せるため cited source content を書き換えません。
- Private key を request、display、copy、persist しません。有効 signature は trusted public key に対する matching key control を証明しますが identity や trusted time ではありません。
- Verification、explanation、comparison、receipt verification は read-only です。Explicit approval なしに ADR、package、report、backup を overwrite しません。
- Explicit configuration/authorization なしに model/embedding provider を enable したり source content を transfer したりしません。
- 選択 audience を超えて source content、local path、credential、package を expose しません。Bundled explanation は quote ではなく hash と span location を返します。
