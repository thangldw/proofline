# OpenAI plugin submission record

Observation date: 2026-08-24

## English

### Repository facts

- OpenAI plugin ID: `plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Update submission ID: `appsub_6a8ab28cfc44819197f0057d5f274cc4`
- Repository/plugin manifest version: `2.0.0`
- Directory URL: `https://chatgpt.com/plugins/plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Bundle type: skills-only, local, no authentication, no hosted MCP endpoint.
- Submitted ZIP SHA-256 recorded for the 2.0.0 review: `5d3abb3412b2eff44dc05eed30641cd4884441a54958898ff72441526216287f`.

### External state

The last authenticated submission observation in the retained evidence was: 2.0.0 submitted for review on 2026-08-23; public version 1.0.1 remained approved while the update awaited review. On 2026-08-24 an unauthenticated request to the directory URL returned HTTP 403, so this rebuild did not independently confirm the currently public version. Treat approval/publication as external state, not a repository guarantee.

### Reviewer workflow

Use Python 3.11 or newer and `skills/manage-evidence-decisions/scripts/proofline_package.py`. The bundled verifier uses the standard library, creates no product account or local database, and requires no network, model credential, or dependency installation.

1. Verify a DEP and report artifact ID, root hash, and citation count without mutation.
2. Explain verified provenance without returning source/quote content.
3. Verify both packages before a content-free diff.
4. Verify a review receipt against its exact package root.
5. For Ed25519, use an installed Proofline 2.0.0 runtime with the exact package, optional receipt, and independently trusted public key. The bundled verifier does not verify Ed25519 and the plugin never reads private keys.

Reject requests to falsify stale evidence, overwrite the only package without confirmation, disclose confidential source content, or upload local sources without explicit provider configuration and authorization.

### Listing boundary

Proofline reviews evidence-backed engineering decisions, preserves exact cited spans, verifies portable packages, and compares verified versions. It does not provide hosted sync, shared workspaces, OAuth, organization identity, remote MCP, trusted time, or revocation.

## Tiếng Việt

### Repository fact

- OpenAI plugin ID: `plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Update submission ID: `appsub_6a8ab28cfc44819197f0057d5f274cc4`
- Version repository/plugin manifest: `2.0.0`
- Directory URL: `https://chatgpt.com/plugins/plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Loại bundle: skills-only, local, không authentication, không hosted MCP endpoint.
- Submitted ZIP SHA-256 đã ghi cho review 2.0.0: `5d3abb3412b2eff44dc05eed30641cd4884441a54958898ff72441526216287f`.

### External state

Quan sát submission authenticated cuối cùng trong evidence giữ lại là: 2.0.0 submitted for review ngày 2026-08-23; public version 1.0.1 vẫn approved khi update chờ review. Ngày 2026-08-24, request unauthenticated tới directory URL trả HTTP 403, nên đợt rebuild này không tự xác nhận version đang public. Xem approval/publication là external state, không phải guarantee của repository.

### Reviewer workflow

Dùng Python 3.11 trở lên và `skills/manage-evidence-decisions/scripts/proofline_package.py`. Bundled verifier dùng standard library, không tạo product account hoặc local database và không cần network, model credential hoặc dependency installation.

1. Verify DEP và báo artifact ID, root hash, citation count mà không mutate.
2. Explain verified provenance mà không trả source/quote content.
3. Verify cả hai package trước content-free diff.
4. Verify review receipt với đúng package root.
5. Với Ed25519, dùng runtime Proofline 2.0.0 đã cài cùng exact package, receipt tùy chọn và trusted public key độc lập. Bundled verifier does not verify Ed25519 và plugin không bao giờ đọc private key.

Từ chối yêu cầu làm sai stale evidence, overwrite only package không confirmation, disclose confidential source content hoặc upload local source khi chưa explicit provider configuration và authorization.

### Listing boundary

Proofline review engineering decision có evidence, giữ exact cited span, verify portable package và compare verified version. Nó không cung cấp hosted sync, shared workspace, OAuth, organization identity, remote MCP, trusted time hoặc revocation.

## 日本語

### Repository fact

- OpenAI plugin ID：`plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Update submission ID：`appsub_6a8ab28cfc44819197f0057d5f274cc4`
- Repository/plugin manifest version：`2.0.0`
- Directory URL：`https://chatgpt.com/plugins/plugins_6a6efdf2ccbc81919ebb4cb01805ebaa`
- Bundle type：skills-only、local、authentication なし、hosted MCP endpoint なし。
- 2.0.0 review 用に記録された submitted ZIP SHA-256：`5d3abb3412b2eff44dc05eed30641cd4884441a54958898ff72441526216287f`。

### External state

保持 evidence 内の最後の authenticated submission observation は、2.0.0 が 2026-08-23 に review 提出され、update の review 待ち中は public version 1.0.1 が approved のままだったというものです。2026-08-24 の directory URL への unauthenticated request は HTTP 403 を返したため、この rebuild は現在 public な version を独立確認していません。Approval/publication は external state であり repository guarantee ではありません。

### Reviewer workflow

Python 3.11 以上と `skills/manage-evidence-decisions/scripts/proofline_package.py` を使います。Bundled verifier は standard library のみを使い、product account や local database を作らず、network、model credential、dependency installation を必要としません。

1. DEP を verify し、mutation せず artifact ID、root hash、citation count を報告します。
2. Source/quote content を返さず verified provenance を explain します。
3. Content-free diff の前に両 package を verify します。
4. Review receipt を正確な package root に対して verify します。
5. Ed25519 には installed Proofline 2.0.0 runtime、exact package、任意 receipt、独立に trusted public key を使います。Bundled verifier does not verify Ed25519 であり、plugin は private key を読みません。

Stale evidence の偽造、confirmation なしの only package overwrite、confidential source content の disclosure、explicit provider configuration/authorization なしの local source upload は拒否します。

### Listing boundary

Proofline は evidence-backed engineering decision を review し、exact cited span を保持し、portable package を verify し、verified version を比較します。Hosted sync、shared workspace、OAuth、organization identity、remote MCP、trusted time、revocation は提供しません。
