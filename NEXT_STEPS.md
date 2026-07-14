# Proofline — công việc còn lại

**Cập nhật:** 2026-07-14
**Trạng thái hiện tại:** repository public, platform-aware wheel launcher, support/ownership policy,
installed-wheel macOS lifecycle, backup restore/rollback, OS-keyring qualification receipt,
portable evidence archive v2, experimental Tauri shell, Studio evidence packages, real-Windows
release workflow và private-pilot aggregate analyzer đã hoàn thành cho `v0.14.17`; Windows receipt,
signed packaging, production
qualification, real-model evaluation và external pilot vẫn mở.
**Mục đích:** điểm tiếp tục công việc cho ngày 2026-07-14. Đây là backlog thực tế; không coi mục “planned” là đã hoàn thành.

## Mở rộng evidence-first đã được chấp thuận

ADR 0004 giới hạn các đề xuất “bộ não” thành những lát cắt vẫn dùng immutable source identity và
exact source span. Thứ tự phát hành tiếp theo:

### v0.12 — Personal Second Brain

- [x] Quick-capture ghi chú Markdown với stable `note://` identity.
- [x] Mỗi lần sửa nội dung tạo source version bất biến; citation lịch sử vẫn mở được.
- [x] Parse deterministic hashtag và `[[wiki-link]]` kèm exact offsets.
- [x] Backlink chỉ ra source version và exact span tạo liên kết.
- [x] Search, deletion cascade, workspace isolation, API và web tests.

### Các mốc sau v0.12

- [x] **v0.13 Learning Brain:** flashcard deterministic từ `Q:`/`A:` có immutable exact evidence,
  append-only review history, scheduling state và superseded handling.
- [x] **v0.14 Third Brain AI:** grounded action proposal giữ model run + immutable exact citations,
  human accept/reject audit và không autonomous write-back.
- [ ] **v0.15 Team Brain:** chỉ bắt đầu sau authentication, RBAC, organization audit và permission-aware retrieval.

Không mốc nào ở trên cho phép rich-text editor, canvas, graph database hoặc generic agent.

### v0.14.1 — usability/reliability follow-up

- [x] Hiển thị hashtag, resolved/unresolved wiki-link và exact-version backlink trong Notes UI.
- [x] Title-only note edit không tạo source revision hoặc thay ingestion timestamp giả.
- [x] Study queue mặc định chỉ tải card đã đến hạn.
- [x] Expose append-only study review history qua workspace-scoped API.

### v0.14.2 — note history usability

- [x] Lọc note local theo title hoặc deterministic hashtag.
- [x] Liệt kê revision theo version number, content length và immutable identity.
- [x] Mở nội dung revision read-only qua workspace-scoped source/version API.
- [x] Portable JSON schema v2 giữ study cards/reviews, grounded proposals/citations, Studio
  artifacts/citations, workspace scope và chunk identities; import schema v1 vẫn được nâng cấp an toàn.

### v0.14.5 — Evidence-first Studio

- [x] Studio hub có đủ 9 loại: audio overview, presentation, video overview, mind map, report,
  flashcards, quiz, infographic và data table.
- [x] Persist artifact theo immutable source version; tạo lại cùng version/kind là idempotent.
- [x] Mọi item giữ exact offsets, lines, quote hash và mở được evidence trong UI.
- [x] Audio phát bằng browser speech; slide/video có preview tương tác; quiz/flashcard có trạng thái học.
- [x] Xóa source báo trước và cascade Studio artifact/citation.
- [x] Evidence package download có manifest immutable citation, `.pptx`, PNG infographic, CSV,
  Markdown, narration script và storyboard HTML; export fail-closed khi citation không còn exact.
- [ ] Render MP3/MP4 và model-enhanced generation để lại cho mốc media production sau khi có
  provider/dữ liệu thật.

### v0.14.6 — Explicit offline model-comparison mock

- [x] Preflight và comparison mock chỉ chạy khi có `--allow-mock`.
- [x] Scripted provider chạy in-process, không gọi QwenCloud hoặc Ollama.
- [x] Fixture extraction/grounded-QA và comparison plan được version hóa.
- [x] Receipt giữ qualification `mock_integration`; điểm fixture không được tính là model quality.

### v0.14.7 — Public hygiene and production gate matrix

- [x] Xóa contributor-machine absolute paths khỏi design QA.
- [x] Cập nhật security support boundary theo release hiện tại.
- [x] Sửa tài liệu portable merge để khớp behavior đã phát hành từ `v0.8.0`.
- [x] Định nghĩa production target local desktop và receipt bắt buộc cho từng gate.

### v0.14.8 — Installed-release platform receipt

- [x] Khóa SHA-256 của wheel và Git revision trong receipt versioned.
- [x] Ghi OS, machine architecture, Python và Proofline version.
- [x] Chạy installed server start/ready/web/graceful-stop trên artifact đã cài.
- [x] Chạy immutable evidence, export/import, backup/restore và integrity trên cùng environment.
- [x] Upload receipt cùng release assets và đưa receipt vào `SHA256SUMS`.

### v0.14.9 — OS-backed provider secrets

- [x] Thêm opt-in macOS Keychain và Windows Credential Locker qua `PROOFLINE_SECRET_STORE=os_keyring`.
- [x] Giữ file mode quyền owner-only làm mặc định cho local development.
- [x] Migrate key cũ khỏi JSON, hỗ trợ replace/remove và rollback file + keyring cùng nhau.
- [x] Hiển thị storage mode và thao tác xóa key trong Settings mà không trả lại secret.
- [x] Ghi set/read/delete của real macOS Keychain vào installed-release receipt.

### v0.14.10 — Verified backup restore and rollback

- [x] Thêm CLI restore backup đã verify vào đúng SQLite target được cấu hình.
- [x] Bắt buộc rollback copy khi thay database hiện có; không overwrite rollback cũ.
- [x] Refuse path trùng, SQLite sidecar và candidate sai schema trước khi publish.
- [x] Atomic replace với quyền owner-only và post-restore verification.
- [x] Installed-release receipt restore về snapshot cũ rồi reverse bằng rollback copy.

### v0.14.11 — Public support and ownership policy

- [x] Thêm root support policy với supported scope, safe issue report và no-SLA boundary.
- [x] Ghi data-loss escalation, backup responsibility và upgrade/database rollback flow.
- [x] Định nghĩa release cadence pre-alpha và latest-release-only support.
- [x] Ghi current maintainer cùng production ownership gaps chưa được nhận.
- [x] Chuyển GitHub repository sang public sau khi chủ sở hữu xác nhận trực tiếp.

### v0.14.12 — Public experimental repository

- [x] Chuyển `thangldw/proofline` sang public và xác nhận lại visibility qua GitHub API.
- [x] Xác nhận default branch, Issues, description và topics công khai.
- [x] Cập nhật release/readiness documentation để không còn tuyên bố repository private.
- [x] Giữ nhãn experimental pre-alpha; không suy diễn public thành production-ready.

### v0.14.13 — Platform-aware installed-wheel launcher

- [x] Thêm `proofline launch` dùng loopback và dynamic port, mở bundled UI bằng default browser.
- [x] Chọn application-data directory chuẩn theo macOS, Windows và XDG Linux.
- [x] Bật OS keyring mặc định cho launcher trên macOS/Windows; không ghi secret vào receipt.
- [x] Ready-file nằm trong app state và được xóa khi shutdown sạch.
- [x] Giữ ranh giới rõ: đây là wheel launcher, không phải native/signed desktop application.

## Việc nên làm đầu tiên ngày mai

### P0 — Git repository ingestion dạng read-only

Đây là source family tiếp theo đã được chọn trong product brief và là khoảng trống lớn nhất đối với định vị Engineering Decision Memory.

Phạm vi lát cắt đầu tiên:

- [x] Viết ADR cho identity và provenance của Git source.
- [x] Nhập một local Git repository đã được người dùng đăng ký rõ ràng.
- [x] Thu thập tracked Markdown/text files tại một commit xác định.
- [x] Thu thập commit metadata tối thiểu: SHA, author, authored time, subject và body.
- [x] Dùng `repository path + commit SHA + file path` làm locator ổn định.
- [x] Giữ exact line/span evidence cho nội dung file tại commit đã nhập.
- [x] Re-scan phải idempotent; commit cũ và citation lịch sử không bị ghi đè.
- [x] Search và grounded answer trả source title, commit SHA, path và exact lines.
- [x] Source inventory phân biệt Markdown upload, folder file, Git file và Git commit.
- [x] Xóa repository source xóa chunks/index/embeddings/memories/evidence dẫn xuất.
- [x] Thêm fixture Git repository tổng hợp; không dùng repository riêng tư hoặc dữ liệu pilot thật trong test.
- [x] Thêm API, integration, web contract và migration tests tương ứng.
- [x] Cập nhật README, architecture, roadmap và changelog sau khi behavior thực sự chạy được.

Không nằm trong lát cắt đầu tiên:

- GitHub OAuth, webhook hoặc write-back.
- Pull request review bot.
- Clone repository qua network.
- GitLab và hosted enterprise connectors.

Điều kiện hoàn thành:

```text
Import local repo → index immutable commit/file sources → search → grounded answer
→ mở exact commit/path/line evidence → re-scan không trùng → delete cascade sạch
```

## P1 — Hoàn thiện lõi sản phẩm

### Temporal decision relations

- [x] Chốt ontology tối thiểu cho `supersedes`, `implements`, `contradicts`, `based_on`, `considered`.
- [x] Thêm relation model, migration, API và audit history.
- [x] Phân biệt thời gian ingest với `valid_from`/`valid_to` của quyết định.
- [x] Cho phép đánh dấu một decision bị thay thế bởi decision khác.
- [x] Retrieval ưu tiên decision đang có hiệu lực nhưng vẫn cho phép xem lịch sử.
- [x] Hiển thị decision timeline và evidence cho từng transition.
- [x] Phát hiện candidate contradiction/staleness; không tự động sửa memory đã được chấp nhận.

### Provider configuration và reliability

- [x] Thêm Settings UI cho Qwen, DeepSeek, Ollama/vLLM và OpenAI-compatible endpoint.
- [x] Health check riêng cho generation, embedding và reranking capability.
- [x] Hiển thị degraded mode khi provider không sẵn sàng.
- [x] Thêm bounded transport retry cho lỗi transient.
- [x] Thêm model-run dead-letter/retry workflow thay vì chỉ repair structured output.
- [x] Không tự động chuyển từ local provider sang remote provider.
- [x] Lưu provider API key bằng OS keyring cho desktop, có migration, rotation/removal và rollback.

### Retrieval quality

- [x] Thiết kế reranker interface độc lập provider.
- [x] Benchmark một reranker local/cheap trên evaluation corpus trước khi chọn mặc định.
- [x] Thêm optional cross-encoder reranking sau RRF.
- [x] Đánh giá semantic entailment/contradiction check cho answer statements.
- [x] Thay full JSON cosine scan bằng vector candidate index trước khi tuyên bố scale.
- [x] Benchmark latency, memory và index-update cost; lưu receipt có version/model/config.

### Ingestion và portability còn thiếu

- [x] Benchmark polling watcher; giữ polling vì median no-op 1.000 file là 403 ms, dưới ngưỡng
  1.000 ms đã khóa trước (`evals/benchmarks/folder-watcher-1000-v1.json`).
- [x] Thiết kế coordination cho nhiều API worker bằng SQLite workspace lease có expiry.
- [x] Hỗ trợ portable import vào database không rỗng bằng explicit merge/remap workflow.
- [x] Không hỗ trợ overwrite phá hủy dữ liệu; portable merge luôn preview, remap và rollback atomically.

### Workspace và packaging

- [x] Thêm workspace abstraction và default local workspace tương thích dữ liệu cũ.
- [x] Quy định workspace-scoped source identity, search, model runs, audit và deletion.
- [ ] Xác minh Windows trong CI hoặc máy thật.
- [x] Thêm PowerShell local-release workflow cho Windows thật, MSI/NSIS, installed-wheel +
  Credential Locker receipt; tooling từ chối tạo Windows receipt trên OS khác.
- [ ] Hoàn thiện production packaging; chưa tuyên bố production support.
- [x] Hoàn thiện embedded start/ready/stop, data-directory, migration/recovery và same-origin web
  lifecycle làm nền cho native wrapper.
- [x] Bundle reviewed web UI vào wheel và smoke-test executable đã cài để chạy local bằng một lệnh.
- [x] Đánh giá Tauri desktop packaging; ADR 0003 hoãn triển khai cho đến khi Windows, lifecycle
  API/web và production support boundary được chứng minh.
- [x] Triển khai experimental Tauri v2 shell + frozen sidecar, dynamic loopback readiness và
  private graceful shutdown; macOS `.app/.dmg` đã build cục bộ nhưng chưa notarize.

## P1 — Đánh giá bằng model và dữ liệu thật

### Real-model comparison

- [ ] Chọn ít nhất một remote/cheap model, ví dụ Qwen hoặc DeepSeek.
- [ ] Chọn ít nhất một local model qua Ollama/vLLM.
- [ ] Khóa model version, prompt version và provider configuration trong report.
- [ ] Đo extraction precision/recall cho bốn memory kinds.
- [ ] Đo grounded answer citation precision, abstention, latency và estimated cost.
- [ ] Không dùng vài demo thành công để tuyên bố chất lượng tổng quát.

Nền tảng preflight đã triển khai ngày 2026-07-13:

- [x] Manifest versioned bắt buộc có ít nhất một provider local và một provider remote.
- [x] Receipt khóa dataset SHA-256, declared model revision, prompt version và token pricing.
- [x] Credential chỉ đọc từ tên biến môi trường; receipt không ghi secret.
- [x] Endpoint/credential failure được ghi `blocked` với error code và CLI exit khác 0.
- [x] Runner dùng production extraction/grounded paths và cô lập failure theo provider.
- [x] Aggregate precision/recall theo kind, citation, abstention, latency, token và estimated cost.
- [x] Mock API-key/transport integration có qualification riêng, không thể bị coi là real evidence.
- [x] Mock preflight/comparison có CLI `--allow-mock`, fixture versioned và không gọi network.
- [ ] Qwen workspace key đã có nhưng region endpoint/model revision chưa được xác nhận; máy hiện
  tại vẫn chưa có Ollama model.
- [ ] Chưa chạy extraction/grounded comparison với model thật; mock không được tính là quality evidence.

### Problem corpus và pilot

- [ ] Tuyển 5 design partners hoặc engineering teams.
- [ ] Phỏng vấn 5–10 engineers.
- [ ] Thu thập tối thiểu 25 câu hỏi thật có permission và relevance judgments.
- [ ] Có ít nhất 10 câu hỏi liên quan decision thay đổi theo thời gian.
- [ ] Ghi baseline thủ công: thời gian trả lời, số nguồn phải mở và confidence.
- [ ] Chạy pilot hàng tuần và đóng băng report theo protocol trong `docs/pilot-protocol.md`.
- [x] Thêm analyzer cho frozen private pilot: kiểm SHA-256/ID/FK, aggregate citation/usefulness/time,
  weekly usage và WTP; output không chứa raw question/source/identity.
- [ ] Không trộn dữ liệu pilot riêng tư vào repository công khai.

Go/no-go metrics chưa được chứng minh:

- [ ] Citation precision ≥ 90% trên pilot dataset.
- [ ] Useful-answer rate ≥ 65%.
- [ ] Median time-to-context cải thiện ≥ 50%.
- [ ] Ít nhất 3/5 teams sử dụng hàng tuần.
- [ ] Ít nhất 2 teams thể hiện willingness-to-pay cụ thể.

## P2 — Source và connector tiếp theo

Chỉ bắt đầu sau khi Git read-only ingestion và pilot ban đầu chứng minh giá trị:

- [ ] GitHub/GitLab repository, issue và pull request connectors.
- [ ] ADR/Markdown import UX hoàn chỉnh hơn.
- [ ] PDF có text layer.
- [ ] Meeting transcript và timestamp evidence.
- [ ] Jira/Linear.
- [ ] Slack/Teams.
- [ ] Confluence/SharePoint.
- [ ] Incident và CI/CD metadata.

Mọi connector phải có:

```text
stable identity + immutable revision + exact locator + indexing status
+ idempotent update + deletion cascade + permission boundary + fixtures/tests
```

## P3 — Tính năng sau MVP

- [ ] Desktop application và mobile capture.
- [ ] Multi-device sync và backup service.
- [ ] Team/shared workspace.
- [ ] Authentication, RBAC và organization audit.
- [ ] Managed model inference và usage accounting.
- [ ] Billing, subscription và commercial control plane.
- [ ] Enterprise deployment, SSO, retention policy và data residency.
- [ ] Proactive stale-decision/contradiction notifications.

Các phần vẫn chủ động không làm sớm:

- Rich-text/Notion-style editor.
- Canvas và graph visualization cầu kỳ.
- Generic agent builder.
- Social/community feed.
- Plugin marketplace.
- Autonomous write-back vào source.

## Quyết định sản phẩm và thương mại còn mở

- [ ] Chốt ICP đầu tiên bằng pilot evidence: individual senior engineers hay team 5–50 người.
- [ ] Chốt paid surface: managed sync, managed AI, team collaboration hoặc enterprise controls.
- [ ] Chốt license dài hạn: giữ MIT hay chuyển sang cấu trúc open-core/dual license cho contribution tương lai.
- [ ] Nếu thay license, cần tư vấn pháp lý và contributor-rights strategy; không đổi license âm thầm.
- [ ] Xác minh trademark/domain/package names cho Proofline.
- [x] Chuẩn bị alpha release criteria và support boundary rõ ràng.

## Checklist bắt đầu phiên làm việc ngày mai

```bash
git status --short --branch
git pull --ff-only
make setup
make test
make check
make eval
```

Sau đó chọn một gate chưa đóng có đủ môi trường/chứng cứ; không lặp lại lát cắt Git đã phát hành.

## Definition of Done cho mỗi công việc

- [ ] Behavior có acceptance criteria kiểm thử được.
- [ ] Exact provenance vẫn đúng qua mọi transformation.
- [ ] Có migration cho persistent schema change.
- [ ] Failure state hiển thị được; không nuốt lỗi ingestion/extraction.
- [ ] Re-run/retry không tạo duplicate.
- [ ] Deletion bao phủ derived chunks, indexes, embeddings, memories và evidence.
- [ ] Local/offline mode vẫn hoạt động nếu feature không bắt buộc network.
- [ ] Tests, lint, typecheck, build và eval liên quan đều pass.
- [ ] Documentation phân biệt implemented với planned.
- [ ] Commit nhỏ, message rõ và push lên nhánh `codex/` trước khi kết thúc phiên.
