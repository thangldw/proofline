# OpenAI plugin submission record

Observation date: 2026-08-24

## English

### Repository facts

- OpenAI plugin ID: `plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Published v2.0.2 submission ID: `appsub_6a8ba7cb85dc81919f961b5ca9a9f62d`
- Repository/plugin manifest version: `2.0.2`
- Directory URL: `https://chatgpt.com/plugins/plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Bundle type: skills-only, local, no authentication, no hosted MCP endpoint.
- Submitted v2.0.2 ZIP SHA-256: `c6e8e83ba66e78811dcd6d99011d6454abb367969abf77ca7dbbd1803df8360`.
- Historical submitted v2.0.1 ZIP SHA-256: `67ab5b9dc61160537f19f99041a141cb7f6abdaf0c5da1044b741501f8888560`.

### External state

Authenticated portal and public Directory observation at 2026-08-24T11:25+09:00: submission `appsub_6a8ba7cb85dc81919f961b5ca9a9f62d` passed scanning and review, and version 2.0.2 was published at the stable plugin URL. The public page showed the expected three prompts, `Manage Evidence Decisions` skill, `Read, Write` capabilities, developer `DUC THANG LUU`, and version 2.0.2. The accidental duplicate draft plugin was deleted, and the portal then listed one Proofline plugin. Treat approval/publication as external state, not a repository guarantee.

### Reviewer workflow

Use Python 3.11 or newer and `skills/manage-evidence-decisions/scripts/proofline_package.py`. The bundled verifier uses the standard library, creates no product account or local database, and requires no network, model credential, or dependency installation.

1. Verify a DEP and report artifact ID, root hash, and citation count without mutation.
2. Explain verified provenance without returning source/quote content.
3. Verify both packages before a content-free diff.
4. Verify a review receipt against its exact package root.
5. For Ed25519, use an installed Proofline 2.0.2 runtime with the exact package, optional receipt, and independently trusted public key. The bundled verifier does not verify Ed25519 and the plugin never reads private keys.

Reject requests to falsify stale evidence, overwrite the only package without confirmation, disclose confidential source content, or upload local sources without explicit provider configuration and authorization.

### Listing boundary

Proofline reviews evidence-backed engineering decisions, preserves exact cited spans, verifies portable packages, and compares verified versions. It does not provide hosted sync, shared workspaces, OAuth, organization identity, remote MCP, trusted time, or revocation.

## Tiếng Việt

### Repository fact

- OpenAI plugin ID: `plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Submission ID v2.0.2 đã publish: `appsub_6a8ba7cb85dc81919f961b5ca9a9f62d`
- Version repository/plugin manifest: `2.0.2`
- Directory URL: `https://chatgpt.com/plugins/plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Loại bundle: skills-only, local, không authentication, không hosted MCP endpoint.
- Submitted ZIP SHA-256 của v2.0.2: `c6e8e83ba66e78811dcd6d99011d6454abb367969abf77ca7dbbd1803df8360`.
- Historical submitted ZIP SHA-256 của v2.0.1: `67ab5b9dc61160537f19f99041a141cb7f6abdaf0c5da1044b741501f8888560`.

### External state

Quan sát authenticated portal và public Directory lúc 2026-08-24T11:25+09:00: submission `appsub_6a8ba7cb85dc81919f961b5ca9a9f62d` đã pass scanning và review; version 2.0.2 đã được publish tại stable plugin URL. Public page hiển thị đúng ba prompt, skill `Manage Evidence Decisions`, capabilities `Read, Write`, developer `DUC THANG LUU` và version 2.0.2. Duplicate draft plugin tạo nhầm đã được xoá; portal sau đó chỉ còn một plugin Proofline. Xem approval/publication là external state, không phải guarantee của repository.

### Reviewer workflow

Dùng Python 3.11 trở lên và `skills/manage-evidence-decisions/scripts/proofline_package.py`. Bundled verifier dùng standard library, không tạo product account hoặc local database và không cần network, model credential hoặc dependency installation.

1. Verify DEP và báo artifact ID, root hash, citation count mà không mutate.
2. Explain verified provenance mà không trả source/quote content.
3. Verify cả hai package trước content-free diff.
4. Verify review receipt với đúng package root.
5. Với Ed25519, dùng runtime Proofline 2.0.2 đã cài cùng exact package, receipt tùy chọn và trusted public key độc lập. Bundled verifier does not verify Ed25519 và plugin không bao giờ đọc private key.

Từ chối yêu cầu làm sai stale evidence, overwrite only package không confirmation, disclose confidential source content hoặc upload local source khi chưa explicit provider configuration và authorization.

### Listing boundary

Proofline review engineering decision có evidence, giữ exact cited span, verify portable package và compare verified version. Nó không cung cấp hosted sync, shared workspace, OAuth, organization identity, remote MCP, trusted time hoặc revocation.

## 日本語

### Repository fact

- OpenAI plugin ID：`plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Published v2.0.2 submission ID：`appsub_6a8ba7cb85dc81919f961b5ca9a9f62d`
- Repository/plugin manifest version：`2.0.2`
- Directory URL：`https://chatgpt.com/plugins/plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Bundle type：skills-only、local、authentication なし、hosted MCP endpoint なし。
- Submitted v2.0.2 ZIP SHA-256：`c6e8e83ba66e78811dcd6d99011d6454abb367969abf77ca7dbbd1803df8360`。
- Historical submitted v2.0.1 ZIP SHA-256：`67ab5b9dc61160537f19f99041a141cb7f6abdaf0c5da1044b741501f8888560`。

### External state

2026-08-24T11:25+09:00 の authenticated portal と public Directory の observation では、submission `appsub_6a8ba7cb85dc81919f961b5ca9a9f62d` は scanning と review に合格し、version 2.0.2 が stable plugin URL に publish されました。Public page は想定された 3 つの prompt、`Manage Evidence Decisions` skill、`Read, Write` capabilities、developer `DUC THANG LUU`、version 2.0.2 を表示しました。誤って作成した duplicate draft plugin は削除され、その後 portal には Proofline plugin が 1 つだけ表示されました。Approval/publication は external state であり repository guarantee ではありません。

### Reviewer workflow

Python 3.11 以上と `skills/manage-evidence-decisions/scripts/proofline_package.py` を使います。Bundled verifier は standard library のみを使い、product account や local database を作らず、network、model credential、dependency installation を必要としません。

1. DEP を verify し、mutation せず artifact ID、root hash、citation count を報告します。
2. Source/quote content を返さず verified provenance を explain します。
3. Content-free diff の前に両 package を verify します。
4. Review receipt を正確な package root に対して verify します。
5. Ed25519 には installed Proofline 2.0.2 runtime、exact package、任意 receipt、独立に trusted public key を使います。Bundled verifier does not verify Ed25519 であり、plugin は private key を読みません。

Stale evidence の偽造、confirmation なしの only package overwrite、confidential source content の disclosure、explicit provider configuration/authorization なしの local source upload は拒否します。

### Listing boundary

Proofline は evidence-backed engineering decision を review し、exact cited span を保持し、portable package を verify し、verified version を比較します。Hosted sync、shared workspace、OAuth、organization identity、remote MCP、trusted time、revocation は提供しません。
