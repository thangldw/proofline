# Proofline documentation rebuild design

Status: approved in chat; awaiting written-spec review
Date: 2026-08-24
Scope: documentation, diagrams, illustrations, public specification prose, plugin instructions, and documentation validation

[English](#english) · [Tiếng Việt](#tiếng-việt) · [日本語](#日本語)

## English

### Objective

Replace the existing documentation system rather than incrementally editing it. Remove superseded prose, Mermaid graphs, raster documentation illustrations, historical internal plans, and obsolete release pages. Rebuild every retained human-facing Markdown document from a new outline, with complete English, Vietnamese, and Japanese sections in that order.

The rewrite must describe the shipped Proofline 2.0.0 boundary accurately: a single-user, local-first application with deterministic provenance, immutable source versions, exact citation spans, decision-review state, transitive impact, portable evidence packages, review receipts, and optional Ed25519 attestations. AI providers remain optional and outside integrity-critical verification.

### Design decision

Use one trilingual file per topic. Every retained human-facing Markdown document follows this order:

1. English — authoritative technical and legal wording.
2. Vietnamese — complete translation, not a summary.
3. Japanese — complete translation, not a summary.

This avoids three parallel link trees while meeting the requirement that every topic is available in all three languages. Stable commands, paths, schema identities, field names, error codes, hashes, and URLs remain unchanged in translations.

Machine-consumed frontmatter remains syntactically valid and uses English for required scalar metadata. Executable Markdown fixtures are source data, not documentation: they will be rewritten with new synthetic content but will not contain three duplicated decisions, because that would change extraction cardinality and exact-span behavior.

### Alternatives considered

1. **One trilingual file per topic — selected.** Lowest link drift, preserves stable public URLs, and keeps translations adjacent for review.
2. **Separate `en`, `vi`, and `ja` trees.** Cleaner single-language reading but triples paths, link checks, and synchronization risk.
3. **English source plus generated translations.** Reduces initial authoring but adds a localization toolchain and makes the requested rewrite dependent on generated content.

### Destructive scope

Delete these superseded artifacts:

- `docs/assets/stale-decision-demo.gif`
- `docs/assets/stale-decision-report.jpg`
- `docs/assets/stale-decision-terminal.png`
- `docs/releases/v1.0.0.md`
- `docs/releases/v1.0.1.md`
- the four pre-rebuild files under `docs/superpowers/plans/` and `docs/superpowers/specs/`, excluding this design and its implementation plan
- all Mermaid blocks in public documentation
- `docs/OPERATIONS.md`, replaced by lowercase `docs/operations.md`
- `docs/submission/DIRECTORY_SUBMISSION.md`, replaced by `docs/submission/openai-plugin.md`

Git history remains the recovery mechanism. No untracked or uncommitted user file may be removed.

Rewrite, rather than preserve copy from, these retained surfaces:

- `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `PRIVACY.md`, `SECURITY.md`, `SUPPORT.md`, and `TERMS.md`
- all retained and newly created files under `docs/`
- `skills/manage-evidence-decisions/SKILL.md` and its Markdown command reference
- the Decision Evidence Package overview, versioning policy, and test-vector guide
- new overview files for the decision-review receipt and signed-attestation specifications
- the bundled example ADR, repository example ADR, and browser E2E Markdown fixture, while preserving their executable test intent

Preserve these non-documentation assets:

- `LICENSE`
- plugin and desktop application icons
- application HTML, bundled JavaScript/CSS, schemas, JSON vectors, PEM fixtures, source code, configuration, and release artifacts

### Replacement information architecture

Top-level public files:

- `README.md` — product boundary, five-minute path, proof points, and documentation map
- `CHANGELOG.md` — compact release history with links to immutable GitHub releases
- `CONTRIBUTING.md` — development workflow and evidence requirements
- `PRIVACY.md`, `SECURITY.md`, `SUPPORT.md`, `TERMS.md` — complete trilingual policy documents; English controls if translations conflict

Documentation hub:

- `docs/README.md` — role-based navigation and status legend
- `docs/getting-started.md` — install, demo, local server, and first verification
- `docs/architecture.md` — boundaries, components, deterministic path, and optional AI boundary
- `docs/decision-lifecycle.md` — decision status, review state, re-anchoring, resolution, and transitive impact
- `docs/evidence-packages.md` — DEP, review receipt, signed attestation, canonicalization, and trust limits
- `docs/cli-reference.md` — command groups, required inputs, outputs, and exit behavior
- `docs/api-reference.md` — API groups, workspace header, local OpenAPI, and mutation boundaries
- `docs/operations.md` — backup, restore, bulk ingest, integrity, keys, and incident handling
- `docs/release-process.md` — qualification, Trusted Publishing, artifact verification, and plugin submission
- `docs/releases/v2.0.0.md` — current immutable release note
- `docs/submission/openai-plugin.md` — external-state snapshot and reviewer instructions

Specification prose:

- rewrite `spec/decision-evidence-package/README.md`
- rewrite `spec/decision-evidence-package/VERSIONING.md`
- rewrite `spec/decision-evidence-package/v1/test-vectors/README.md`
- add `spec/decision-review-receipt/README.md`
- add `spec/signed-attestation/README.md`

### Diagram set

All diagrams use the explicitly approved default Diagram Design profile: paper `#f5f5f5`, ink `#2d3142`, accent `#eb6c36`. Persist the project choice in `.diagram-design` as exactly `profile: default`.

Each deliverable is a static, self-contained HTML file with embedded CSS and inline accessible SVG. It contains English, Vietnamese, and Japanese figures in that order. No PNG, JPG, GIF, Mermaid, external image, or animation is generated.

1. `docs/diagrams/system-architecture.html`
   - Type: architecture
   - Size: `doc-wide`
   - Detail: balanced
   - Audience: engineer
   - Budget: at most eight nodes and ten connectors
   - Cut: detailed API routes, UI screens, and schema fields stay in prose

2. `docs/diagrams/decision-review-lifecycle.html`
   - Type: state machine
   - Size: `doc-wide`
   - Detail: balanced
   - Audience: engineer
   - Budget: at most six states and ten transitions
   - Cut: audit payload fields and HTTP status codes stay in prose

3. `docs/diagrams/evidence-verification.html`
   - Semantic pattern: secure paved road
   - Type: architecture
   - Size: `doc-wide`
   - Detail: balanced
   - Audience: engineer
   - Budget: at most eight nodes and ten connectors
   - Cut: canonical JSON field lists and mutation vectors stay in specification prose

### Content rules

- State implemented facts separately from limitations and future work.
- Do not call a hash a signature or a valid signature an identity proof.
- Do not claim hosted sync, shared workspaces, OAuth, organization identity, trusted time, revocation, or remote MCP.
- Preserve the distinction between historical decision status and current evidence-review state.
- Commands must be executable from the documented context and use `proofline-evidence` for the PyPI distribution while retaining `proofline` for the CLI and import package.
- Benchmark evidence must remain labeled synthetic and not a hosted/team production benchmark.
- External review or publication status must include an observation date.
- Avoid duplicated narrative across files; link to the authoritative topic.
- No placeholders, marketing filler, screenshots, decorative diagrams, or undocumented external dependencies.

### Validation design

Add a deterministic documentation checker and regression tests that fail when:

- a required documentation file is missing;
- a retained human-facing Markdown file lacks English, Vietnamese, or Japanese in the required order;
- a Mermaid fence or documentation raster asset is present;
- a repository-relative Markdown link is broken;
- a required public URL or package/CLI distinction is lost;
- a diagram fails the Diagram Design accessible-SVG and single-file checks;
- a removed legacy path returns to the tree.

Verification sequence:

1. documentation checker and targeted public/plugin tests;
2. Diagram Design `self_check.py` for every HTML diagram;
3. geometry review and browser rendering at desktop and narrow widths;
4. package and plugin conformance;
5. full Python, web, egress, audit, and browser E2E gates;
6. clean worktree and exact diff manifest.

### Delivery sequence

Work in an isolated `codex/` branch and linked worktree. Commit small, reviewable units:

1. documentation contract and deletion manifest;
2. public entry points and policies;
3. core technical documentation;
4. specification and plugin documentation;
5. diagrams;
6. fixtures, links, and final validation.

Do not publish a new PyPI, GitHub, or plugin version as part of this documentation-only task. Release publication requires a separate version decision because version 2.0.0 artifacts are immutable.

### Acceptance criteria

- Every retained human-facing Markdown topic has complete English, Vietnamese, and Japanese sections in that order.
- No old documentation raster, Mermaid graph, v1 release page, or pre-rebuild internal plan/spec remains.
- All three trilingual HTML diagrams pass the skill self-check and visual inspection.
- Runtime fixtures still exercise deterministic extraction, exact spans, and hostile-markup inertness.
- Public package, legal, plugin, and specification links resolve.
- Full repository gates pass without weakening existing assertions.
- The final report lists deleted, replaced, added, preserved, and verified artifacts separately.

## Tiếng Việt

### Mục tiêu

Thay thế hệ thống tài liệu hiện tại thay vì chỉnh sửa nối tiếp. Xoá nội dung lỗi thời, Mermaid graph, hình raster dùng cho tài liệu, plan nội bộ lịch sử và trang release đã cũ. Viết lại mỗi tài liệu Markdown dành cho người đọc theo outline mới, với ba phần English, Vietnamese và Japanese đầy đủ theo đúng thứ tự đó.

Bộ tài liệu mới phải mô tả chính xác phạm vi Proofline 2.0.0 đã phát hành: ứng dụng local-first cho một người dùng, có provenance xác định, phiên bản nguồn bất biến, citation exact-span, trạng thái decision review, transitive impact, evidence package portable, review receipt và attestation Ed25519 tùy chọn. AI provider chỉ là lớp tùy chọn và nằm ngoài đường xác minh integrity quan trọng.

### Quyết định thiết kế

Mỗi chủ đề dùng một file có đủ ba ngôn ngữ:

1. English — nội dung kỹ thuật và pháp lý có hiệu lực chính.
2. Vietnamese — bản dịch đầy đủ, không phải tóm tắt.
3. Japanese — bản dịch đầy đủ, không phải tóm tắt.

Cấu trúc này tránh ba cây link song song, đồng thời bảo đảm mọi chủ đề có đủ ba ngôn ngữ. Command, path, schema identity, field, error code, hash và URL giữ nguyên trong bản dịch.

Frontmatter do máy đọc phải giữ cú pháp hợp lệ và dùng English cho scalar metadata bắt buộc. Markdown fixture có thể thực thi là source data, không phải tài liệu: chúng sẽ được viết lại bằng nội dung synthetic mới nhưng không nhân ba decision, vì làm vậy sẽ thay đổi số lượng extraction và hành vi exact span.

### Các phương án đã xem xét

1. **Một file ba ngôn ngữ cho mỗi chủ đề — được chọn.** Ít link drift nhất, giữ URL công khai ổn định và đặt các bản dịch cạnh nhau để review.
2. **Ba cây `en`, `vi`, `ja`.** Đọc từng ngôn ngữ sạch hơn nhưng tăng gấp ba path, link check và rủi ro lệch nội dung.
3. **English source cùng bản dịch generate.** Giảm công viết ban đầu nhưng tạo thêm localization toolchain và khiến yêu cầu viết lại phụ thuộc nội dung sinh tự động.

### Phạm vi xoá

Xoá các artifact đã lỗi thời sau:

- `docs/assets/stale-decision-demo.gif`
- `docs/assets/stale-decision-report.jpg`
- `docs/assets/stale-decision-terminal.png`
- `docs/releases/v1.0.0.md`
- `docs/releases/v1.0.1.md`
- bốn file trước đợt rebuild trong `docs/superpowers/plans/` và `docs/superpowers/specs/`, ngoại trừ design này và implementation plan của nó
- toàn bộ Mermaid block trong tài liệu công khai
- `docs/OPERATIONS.md`, thay bằng chữ thường `docs/operations.md`
- `docs/submission/DIRECTORY_SUBMISSION.md`, thay bằng `docs/submission/openai-plugin.md`

Git history là cơ chế khôi phục. Không được xoá file untracked hoặc file người dùng đã sửa nhưng chưa commit.

Viết lại, không giữ nguyên nội dung cũ, trên các bề mặt sau:

- `README.md`, `CHANGELOG.md`, `CONTRIBUTING.md`, `PRIVACY.md`, `SECURITY.md`, `SUPPORT.md` và `TERMS.md`
- toàn bộ file được giữ lại và file mới dưới `docs/`
- `skills/manage-evidence-decisions/SKILL.md` và command reference Markdown của skill
- overview Decision Evidence Package, versioning policy và test-vector guide
- các overview mới cho spec decision-review receipt và signed attestation
- ADR example đi kèm, ADR example của repository và Markdown fixture cho browser E2E, đồng thời bảo toàn mục đích test có thể thực thi

Giữ lại các asset không phải tài liệu sau:

- `LICENSE`
- icon của plugin và desktop application
- HTML ứng dụng, JavaScript/CSS đã bundle, schema, JSON vector, PEM fixture, source code, config và release artifact

### Kiến trúc thông tin thay thế

Các file công khai ở top level:

- `README.md` — phạm vi sản phẩm, luồng dưới năm phút, bằng chứng chính và bản đồ tài liệu
- `CHANGELOG.md` — lịch sử release gọn, có link tới các GitHub release immutable
- `CONTRIBUTING.md` — development workflow và yêu cầu evidence
- `PRIVACY.md`, `SECURITY.md`, `SUPPORT.md`, `TERMS.md` — policy đầy đủ bằng ba ngôn ngữ; English có hiệu lực nếu các bản dịch xung đột

Documentation hub:

- `docs/README.md` — điều hướng theo vai trò và chú giải trạng thái
- `docs/getting-started.md` — cài đặt, demo, local server và lần verify đầu tiên
- `docs/architecture.md` — boundary, component, deterministic path và optional AI boundary
- `docs/decision-lifecycle.md` — decision status, review state, re-anchoring, resolution và transitive impact
- `docs/evidence-packages.md` — DEP, review receipt, signed attestation, canonicalization và giới hạn trust
- `docs/cli-reference.md` — nhóm command, input bắt buộc, output và hành vi exit
- `docs/api-reference.md` — nhóm API, workspace header, local OpenAPI và mutation boundary
- `docs/operations.md` — backup, restore, bulk ingest, integrity, key và xử lý incident
- `docs/release-process.md` — qualification, Trusted Publishing, artifact verification và plugin submission
- `docs/releases/v2.0.0.md` — release note immutable hiện tại
- `docs/submission/openai-plugin.md` — snapshot external state và hướng dẫn reviewer

Spec prose:

- viết lại `spec/decision-evidence-package/README.md`
- viết lại `spec/decision-evidence-package/VERSIONING.md`
- viết lại `spec/decision-evidence-package/v1/test-vectors/README.md`
- thêm `spec/decision-review-receipt/README.md`
- thêm `spec/signed-attestation/README.md`

### Bộ sơ đồ

Dùng profile Diagram Design mặc định đã được duyệt rõ ràng: paper `#f5f5f5`, ink `#2d3142`, accent `#eb6c36`. Ghi lựa chọn của project trong `.diagram-design` với nội dung chính xác `profile: default`.

Mỗi deliverable là file HTML static self-contained, có CSS nhúng và SVG inline accessible. File chứa figure English, Vietnamese và Japanese theo thứ tự đó. Không tạo PNG, JPG, GIF, Mermaid, external image hoặc animation.

1. `docs/diagrams/system-architecture.html`
   - Loại: architecture
   - Kích thước: `doc-wide`
   - Mức chi tiết: balanced
   - Đối tượng: engineer
   - Complexity budget: tối đa tám node và mười connector
   - Phần cắt bỏ: API route chi tiết, màn hình UI và schema field nằm trong prose

2. `docs/diagrams/decision-review-lifecycle.html`
   - Loại: state machine
   - Kích thước: `doc-wide`
   - Mức chi tiết: balanced
   - Đối tượng: engineer
   - Complexity budget: tối đa sáu state và mười transition
   - Phần cắt bỏ: audit payload field và HTTP status code nằm trong prose

3. `docs/diagrams/evidence-verification.html`
   - Semantic pattern: secure paved road
   - Loại: architecture
   - Kích thước: `doc-wide`
   - Mức chi tiết: balanced
   - Đối tượng: engineer
   - Complexity budget: tối đa tám node và mười connector
   - Phần cắt bỏ: danh sách canonical JSON field và mutation vector nằm trong spec prose


### Quy tắc nội dung

- Tách fact đã triển khai khỏi limitation và future work.
- Không gọi hash là signature hoặc gọi signature hợp lệ là bằng chứng identity.
- Không claim hosted sync, shared workspace, OAuth, organization identity, trusted time, revocation hoặc remote MCP.
- Giữ tách biệt historical decision status và evidence-review state hiện tại.
- Command phải chạy được trong context mô tả; dùng `proofline-evidence` cho PyPI distribution và `proofline` cho CLI/import package.
- Benchmark phải ghi rõ synthetic, không phải benchmark hosted/team production.
- Trạng thái review/publication bên ngoài phải kèm ngày quan sát.
- Tránh lặp narrative giữa các file; link tới chủ đề authoritative.
- Không có placeholder, marketing filler, screenshot, sơ đồ trang trí hoặc dependency ngoài không được mô tả.

### Thiết kế xác minh

Thêm checker tài liệu xác định và regression test để fail khi:

- thiếu file tài liệu bắt buộc;
- một Markdown file dành cho người đọc được giữ lại thiếu English, Vietnamese hoặc Japanese theo đúng thứ tự;
- có Mermaid fence hoặc raster asset tài liệu;
- broken repository-relative Markdown link;
- mất public URL bắt buộc hoặc mất phân biệt giữa package và CLI;
- diagram không đạt accessible-SVG và single-file check của Diagram Design;
- path cũ đã xoá quay lại source tree.

Thứ tự xác minh:

1. documentation checker và targeted public/plugin test;
2. Diagram Design `self_check.py` cho từng HTML diagram;
3. geometry review và browser rendering ở desktop và narrow width;
4. package và plugin conformance;
5. full Python, web, egress, audit và browser E2E gate;
6. clean worktree và exact diff manifest.

### Trình tự bàn giao

Làm trong branch `codex/` và linked worktree độc lập. Commit theo các đơn vị nhỏ, dễ review:

1. documentation contract và deletion manifest;
2. public entry point và policy;
3. core technical documentation;
4. spec và plugin documentation;
5. diagram;
6. fixture, link và final validation.

Không phát hành PyPI, GitHub hoặc plugin version mới trong task documentation-only này. Artifact 2.0.0 là immutable; phát hành tiếp cần quyết định version riêng.

### Tiêu chí chấp nhận

- Mỗi chủ đề Markdown dành cho người đọc có đủ ba phần English, Vietnamese và Japanese theo thứ tự.
- Không còn raster tài liệu cũ, Mermaid, v1 release page hoặc internal plan/spec trước rebuild.
- Ba HTML diagram trilingual đạt self-check và visual inspection.
- Fixture vẫn kiểm tra extraction xác định, exact span và hostile markup inert.
- Link package, legal, plugin và spec hoạt động.
- Full repository gate pass mà không làm yếu assertion.
- Báo cáo cuối tách riêng artifact đã xoá, thay thế, thêm mới, giữ lại và xác minh.

## 日本語

### 目的

既存文書を追記修正するのではなく、文書システム全体を置き換えます。古い文章、Mermaid graph、文書用 raster illustration、過去の internal plan、不要な release page を削除します。残す人向け Markdown は新しい outline から書き直し、English、Vietnamese、Japanese の完全な各節をこの順序で配置します。

新文書は、出荷済み Proofline 2.0.0 の境界を正確に説明します。対象は single-user / local-first application であり、決定的 provenance、不変 source version、exact citation span、decision-review state、transitive impact、portable evidence package、review receipt、任意の Ed25519 attestation を備えます。AI provider は任意で、integrity-critical verification の外側にあります。

### 設計判断

各 topic を一つの三言語ファイルにします。

1. English — 技術・法務上の authoritative wording。
2. Vietnamese — 要約ではない完全翻訳。
3. Japanese — 要約ではない完全翻訳。

これにより三つの link tree を避け、公開 URL を安定させながら全 topic を三言語で提供できます。Command、path、schema identity、field name、error code、hash、URL は翻訳内でも変更しません。

機械が読む frontmatter は有効な構文を保ち、必須 scalar metadata は English のままにします。実行可能 Markdown fixture は文書ではなく source data です。新しい synthetic content に書き直しますが、decision を三重化しません。三重化すると extraction cardinality と exact-span behavior が変わるためです。

### 検討した代替案

1. **topic ごとに一つの三言語ファイル — 採用。** Link drift が最小で、安定した公開 URL を維持し、翻訳を隣接して review できます。
2. **`en`、`vi`、`ja` の別 tree。** 単一言語では読みやすい一方、path、link check、同期リスクが三倍になります。
3. **English source と自動生成翻訳。** 初期作業は減りますが localization toolchain が増え、書き直しが生成 content に依存します。

### 破壊的変更の範囲

次の旧 artifact を削除します。

- `docs/assets/stale-decision-demo.gif`
- `docs/assets/stale-decision-report.jpg`
- `docs/assets/stale-decision-terminal.png`
- `docs/releases/v1.0.0.md`
- `docs/releases/v1.0.1.md`
- この design とその implementation plan を除く、`docs/superpowers/plans/` と `docs/superpowers/specs/` にある rebuild 前の四ファイル
- 公開文書内の全 Mermaid block
- `docs/OPERATIONS.md`。小文字の `docs/operations.md` に置換
- `docs/submission/DIRECTORY_SUBMISSION.md`。代わりに `docs/submission/openai-plugin.md` を作成

復旧手段は Git history です。User の untracked file や未 commit の変更を含む file は削除しません。

次の対象は旧文面を保持せず書き直します。

- `README.md`、`CHANGELOG.md`、`CONTRIBUTING.md`、`PRIVACY.md`、`SECURITY.md`、`SUPPORT.md`、`TERMS.md`
- `docs/` 配下で保持する file と新規作成する file の全て
- `skills/manage-evidence-decisions/SKILL.md` とその Markdown command reference
- Decision Evidence Package overview、versioning policy、test-vector guide
- decision-review receipt と signed-attestation specification の新しい overview file
- bundled example ADR、repository example ADR、browser E2E Markdown fixture。ただし実行可能 test の意図は維持

次の非文書 asset は保持します。

- `LICENSE`
- plugin と desktop application の icon
- application HTML、bundle 済み JavaScript/CSS、schema、JSON vector、PEM fixture、source code、configuration、release artifact

### 新しい情報アーキテクチャ

Top-level public file：

- `README.md` — product boundary、五分以内の操作手順、主要 evidence、documentation map
- `CHANGELOG.md` — immutable GitHub release への link を持つ簡潔な release history
- `CONTRIBUTING.md` — development workflow と evidence requirement
- `PRIVACY.md`、`SECURITY.md`、`SUPPORT.md`、`TERMS.md` — 完全な三言語 policy document。翻訳が競合する場合は English を優先

Documentation hub：

- `docs/README.md` — role-based navigation と status legend
- `docs/getting-started.md` — install、demo、local server、最初の verification
- `docs/architecture.md` — boundary、component、deterministic path、optional AI boundary
- `docs/decision-lifecycle.md` — decision status、review state、re-anchoring、resolution、transitive impact
- `docs/evidence-packages.md` — DEP、review receipt、signed attestation、canonicalization、trust limit
- `docs/cli-reference.md` — command group、required input、output、exit behavior
- `docs/api-reference.md` — API group、workspace header、local OpenAPI、mutation boundary
- `docs/operations.md` — backup、restore、bulk ingest、integrity、key、incident handling
- `docs/release-process.md` — qualification、Trusted Publishing、artifact verification、plugin submission
- `docs/releases/v2.0.0.md` — 現行 immutable release note
- `docs/submission/openai-plugin.md` — external-state snapshot と reviewer instruction

Specification prose：

- `spec/decision-evidence-package/README.md` を書き直す
- `spec/decision-evidence-package/VERSIONING.md` を書き直す
- `spec/decision-evidence-package/v1/test-vectors/README.md` を書き直す
- `spec/decision-review-receipt/README.md` を追加する
- `spec/signed-attestation/README.md` を追加する

### 図表セット

明示的に承認された Diagram Design の default profile を使います。paper は `#f5f5f5`、ink は `#2d3142`、accent は `#eb6c36` です。Project の選択を `.diagram-design` に正確に `profile: default` と記録します。

各 deliverable は embedded CSS と accessible inline SVG を持つ static self-contained HTML file です。English、Vietnamese、Japanese の figure をこの順で含みます。PNG、JPG、GIF、Mermaid、external image、animation は生成しません。

1. `docs/diagrams/system-architecture.html`
   - 種類：architecture
   - サイズ：`doc-wide`
   - 詳細度：balanced
   - 対象：engineer
   - Budget：最大八 node、十 connector
   - 除外：詳細 API route、UI screen、schema field は prose に残す

2. `docs/diagrams/decision-review-lifecycle.html`
   - 種類：state machine
   - サイズ：`doc-wide`
   - 詳細度：balanced
   - 対象：engineer
   - Budget：最大六 state、十 transition
   - 除外：audit payload field と HTTP status code は prose に残す

3. `docs/diagrams/evidence-verification.html`
   - Semantic pattern：secure paved road
   - 種類：architecture
   - サイズ：`doc-wide`
   - 詳細度：balanced
   - 対象：engineer
   - Budget：最大八 node、十 connector
   - 除外：canonical JSON field list と mutation vector は specification prose に残す

### 内容規則

- 実装済み fact、limitation、future work を分離します。
- Hash を signature と呼ばず、有効 signature を identity proof と呼びません。
- Hosted sync、shared workspace、OAuth、organization identity、trusted time、revocation、remote MCP を実装済みと claim しません。
- Historical decision status と現在の evidence-review state を分離します。
- Command は記載 context で実行可能にし、PyPI distribution は `proofline-evidence`、CLI/import package は `proofline` とします。
- Benchmark は synthetic と明記し、hosted/team production benchmark と扱いません。
- 外部 review/publication status には観測日を付けます。
- File 間で narrative を重複させず、authoritative topic に link します。
- Placeholder、marketing filler、screenshot、装飾だけの diagram、未記載 external dependency を禁止します。

### 検証設計

決定的 documentation checker と regression test を追加し、次の場合に fail させます。

- 必須 documentation file がない
- 保持する人向け Markdown file に English、Vietnamese、Japanese がこの順で存在しない
- Mermaid fence または documentation raster asset が存在する
- repository-relative Markdown link が壊れている
- 必須 public URL または package/CLI の区別が失われる
- Diagram Design の accessible-SVG check または single-file check に失敗する
- 削除した legacy path が tree に戻る

検証順序：

1. documentation checker と targeted public/plugin test
2. 各 HTML diagram に対する Diagram Design `self_check.py`
3. desktop と narrow width での geometry review と browser rendering
4. package と plugin conformance
5. full Python、web、egress、audit、browser E2E gate
6. clean worktree と exact diff manifest

### 提供順序

独立した `codex/` branch と linked worktree で作業します。次の review 可能な小単位で commit します。

1. documentation contract と deletion manifest
2. public entry point と policy
3. core technical documentation
4. specification と plugin documentation
5. diagram
6. fixture、link、final validation

この documentation-only task では PyPI、GitHub、plugin の新 version を公開しません。2.0.0 artifact は immutable であり、次回公開には別の version decision が必要です。

### 受入条件

- 残すすべての人向け Markdown topic に English、Vietnamese、Japanese の完全な節がこの順で存在すること。
- 旧 raster document、Mermaid、v1 release page、rebuild 前 internal plan/spec が残らないこと。
- 三つの trilingual HTML diagram が self-check と visual inspection を通ること。
- Fixture が deterministic extraction、exact span、hostile markup inertness を引き続き検証すること。
- Package、legal、plugin、spec の link が解決すること。
- Existing assertion を弱めず full repository gate が通ること。
- Final report が deleted、replaced、added、preserved、verified artifact を分けて示すこと。
