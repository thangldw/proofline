# Proofline v2.0.2 Release Design

## English

### Goal

Publish the post-v2.0.1 hardening already merged to `main` as immutable Proofline v2.0.2 artifacts on PyPI, GitHub Releases, and the OpenAI Plugins Directory.

### Scope

- Align every executable and plugin version surface to `2.0.2`.
- Add trilingual v2.0.2 release notes and changelog entries.
- Update current-version documentation while preserving v2.0.1 historical evidence, identifiers, hashes, and release records.
- Qualify the exact release commit with Python, web, egress, E2E, package-conformance, artifact, and dependency-audit gates.
- Publish `proofline-evidence==2.0.2` through the project-scoped PyPI Trusted Publisher, then create immutable tag `v2.0.2` and a GitHub Release from the same commit.
- Build a skills-only plugin ZIP from the same commit, verify it in a clean directory, and submit version `2.0.2` through the authenticated OpenAI portal.

### Boundaries

- Do not rewrite, move, or mutate v2.0.1 artifacts or historical evidence.
- Do not merge pending dependency-major upgrades into this patch.
- Do not publish unsigned desktop artifacts as release-grade assets.
- Do not claim a real-team pilot, hosted-production benchmark, plugin approval, or plugin publication without new external evidence.
- The final portal submission is a representational external action and requires confirmation immediately before Submit.

### Release invariant

PyPI files, Git tag, GitHub assets, source commit, plugin manifest, and submitted plugin ZIP must all resolve to version `2.0.2`; recorded SHA-256 digests must be computed from the exact published or submitted bytes.

## Tiếng Việt

### Mục tiêu

Phát hành phần hardening sau v2.0.1 đã merge vào `main` thành artifact Proofline v2.0.2 bất biến trên PyPI, GitHub Releases và OpenAI Plugins Directory.

### Phạm vi

- Đồng bộ toàn bộ version surface executable và plugin thành `2.0.2`.
- Bổ sung release notes và changelog v2.0.2 theo ba ngôn ngữ.
- Cập nhật tài liệu nói về version hiện tại nhưng giữ nguyên evidence lịch sử, identifier, hash và record của v2.0.1.
- Qualification exact release commit bằng Python, web, egress, E2E, package conformance, artifact và dependency-audit gates.
- Publish `proofline-evidence==2.0.2` qua PyPI Trusted Publisher của project, sau đó tạo tag bất biến `v2.0.2` và GitHub Release từ cùng commit.
- Build plugin ZIP skills-only từ cùng commit, verify trong clean directory và submit version `2.0.2` qua OpenAI portal đã authenticated.

### Ranh giới

- Không rewrite, move hoặc mutate artifact hay historical evidence v2.0.1.
- Không merge dependency major đang chờ vào patch này.
- Không publish desktop artifact unsigned dưới nhãn release-grade.
- Không claim pilot team thật, benchmark hosted production, plugin approval hoặc publication nếu chưa có external evidence mới.
- Submit cuối trên portal là hành động đại diện ra bên ngoài và cần xác nhận ngay trước khi bấm Submit.

### Release invariant

PyPI files, Git tag, GitHub assets, source commit, plugin manifest và plugin ZIP đã submit phải cùng resolve tới version `2.0.2`; SHA-256 phải được tính từ đúng bytes đã publish hoặc submit.

## 日本語

### 目的

`main` に merge 済みの v2.0.1 後 hardening を、不変な Proofline v2.0.2 artifact として PyPI、GitHub Releases、OpenAI Plugins Directory に公開します。

### Scope

- すべての executable / plugin version surface を `2.0.2` に揃えます。
- English、Vietnamese、Japanese の v2.0.2 release notes と changelog を追加します。
- Current-version documentation を更新し、v2.0.1 の historical evidence、identifier、hash、release record は保持します。
- Exact release commit に対して Python、web、egress、E2E、package conformance、artifact、dependency audit gate を実行します。
- Project-scoped PyPI Trusted Publisher で `proofline-evidence==2.0.2` を publish し、同一 commit から不変 tag `v2.0.2` と GitHub Release を作成します。
- 同一 commit から skills-only plugin ZIP を build し、clean directory で verify して、authenticated OpenAI portal から version `2.0.2` を submit します。

### 境界

- v2.0.1 artifact と historical evidence は rewrite、move、mutate しません。
- Pending dependency-major upgrade はこの patch に含めません。
- Unsigned desktop artifact を release-grade として公開しません。
- 新しい external evidence がない real-team pilot、hosted-production benchmark、plugin approval、plugin publication は主張しません。
- Portal の最終 Submit は外部への representational action であり、Submit 直前の確認を必要とします。

### Release invariant

PyPI files、Git tag、GitHub assets、source commit、plugin manifest、submitted plugin ZIP はすべて version `2.0.2` に解決され、SHA-256 は実際に publish / submit した bytes から計算されなければなりません。
