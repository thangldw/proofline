# Architecture

## English

### Boundary

Proofline 2.0.2 is a single-user, local-first application. The authoritative state is local SQLite plus user-controlled files. CLI, local FastAPI, web UI, and desktop shell share the same domain model. There is no hosted control plane, tenant isolation, organization identity, OAuth, or remote MCP.

View the [trilingual system architecture diagram](diagrams/system-architecture.html).

### Deterministic path

1. A file, note, folder scan, or Git import enters through an explicit local action.
2. Ingest normalizes content and stores an immutable source version with hashes and stable offsets.
3. SQLite/FTS indexes retrieval units; citations bind source ID, version ID, offsets, lines, quote, and quote hash.
4. Decisions preserve their historical status and explicit relations. Review refresh compares current sources with stored bindings; impact traversal follows active `based_on` and `implements` edges.
5. Package, receipt, backup, integrity, and attestation verification use deterministic local code and fail-closed error codes.

SQLite transactions protect mutations. Source replacement creates a new version; it does not mutate the cited historical version. A stale check changes review state, not accepted decision history.

### Optional AI boundary

Generation, embeddings, and reranking are optional provider interfaces. A user must configure and invoke them. Model output is recorded as a model run and must pass grounding/structure validation before becoming a candidate. Providers are not required for ingest, exact-span citation checks, decision health, transitive impact, package verification, receipt verification, backup verification, or signed-attestation verification.

### Trust and failure boundary

Hashes detect mutation. Ed25519 verifies a signature against a supplied trusted public key. Neither establishes source truth, identity, trusted time, authorization, or revocation. Verification operates on explicit inputs, reports stable errors, and does not silently repair evidence.

## Tiếng Việt

### Boundary

Proofline 2.0.2 là application single-user, local-first. State authoritative là SQLite local cùng file do người dùng kiểm soát. CLI, FastAPI local, web UI và desktop shell dùng chung domain model. Không có hosted control plane, tenant isolation, organization identity, OAuth hoặc remote MCP.

Xem [sơ đồ system architecture ba ngôn ngữ](diagrams/system-architecture.html).

### Deterministic path

1. File, note, folder scan hoặc Git import đi vào qua explicit local action.
2. Ingest normalize content và lưu phiên bản nguồn bất biến với hash cùng stable offset.
3. SQLite/FTS index retrieval unit; citation gắn source ID, version ID, offset, line, quote và quote hash.
4. Decision giữ historical status và explicit relation. Review refresh so sánh source hiện tại với binding đã lưu; impact traversal đi qua edge `based_on` và `implements` đang active.
5. Package, receipt, backup, integrity và attestation verification dùng deterministic local code cùng fail-closed error code.

SQLite transaction bảo vệ mutation. Thay source tạo version mới; không mutate historical version đã được citation. Stale check thay review state, không thay accepted decision history.

### Optional AI boundary

Generation, embedding và reranking là optional provider interface. Người dùng phải cấu hình và gọi rõ ràng. Model output được ghi thành model run và phải qua grounding/structure validation trước khi thành candidate. Provider không cần thiết cho ingest, exact-span citation check, decision health, transitive impact, package verification, receipt verification, backup verification hoặc signed-attestation verification.

### Trust và failure boundary

Hash phát hiện mutation. Ed25519 verify signature với trusted public key được cung cấp. Không cơ chế nào thiết lập source truth, identity, trusted time, authorization hoặc revocation. Verification xử lý input explicit, báo stable error và không tự repair evidence.

## 日本語

### Boundary

Proofline 2.0.2 は single-user / local-first application です。Authoritative state は local SQLite と user-controlled file です。CLI、local FastAPI、web UI、desktop shell は同じ domain model を共有します。Hosted control plane、tenant isolation、organization identity、OAuth、remote MCP はありません。

[三言語 system architecture diagram](diagrams/system-architecture.html) を参照してください。

### Deterministic path

1. File、note、folder scan、Git import は明示的な local action から入ります。
2. Ingest は content を normalize し、hash と stable offset を持つ immutable source version を保存します。
3. SQLite/FTS は retrieval unit を index し、citation は source ID、version ID、offset、line、quote、quote hash を結び付けます。
4. Decision は historical status と explicit relation を保持します。Review refresh は現在 source と保存 binding を比較し、impact traversal は active な `based_on` / `implements` edge をたどります。
5. Package、receipt、backup、integrity、attestation verification は deterministic local code と fail-closed error code を使います。

SQLite transaction が mutation を保護します。Source replacement は新 version を作り、引用済み historical version を変更しません。Stale check が変えるのは review state で、accepted decision history ではありません。

### Optional AI boundary

Generation、embedding、reranking は optional provider interface です。User が明示的に設定・実行する必要があります。Model output は model run として記録され、candidate になる前に grounding/structure validation を通ります。Provider は ingest、exact-span citation check、decision health、transitive impact、package/receipt/backup/signed-attestation verification には不要です。

### Trust と failure boundary

Hash は mutation を検出します。Ed25519 は指定した trusted public key に対して signature を検証します。どちらも source truth、identity、trusted time、authorization、revocation を確立しません。Verification は明示 input を処理し、stable error を返し、evidence を暗黙 repair しません。
