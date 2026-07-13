# Proofline — công việc còn lại

**Cập nhật:** 2026-07-13  
**Trạng thái hiện tại:** Git read-only vertical slice đã hoàn tất cho `v0.3.0`; các mục P1 và pilot vẫn mở.  
**Mục đích:** điểm tiếp tục công việc cho ngày 2026-07-14. Đây là backlog thực tế; không coi mục “planned” là đã hoàn thành.

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

- [ ] Thêm Settings UI cho Qwen, DeepSeek, Ollama/vLLM và OpenAI-compatible endpoint.
- [ ] Health check riêng cho generation, embedding và reranking capability.
- [ ] Hiển thị degraded mode khi provider không sẵn sàng.
- [ ] Thêm bounded transport retry cho lỗi transient.
- [ ] Thêm model-run dead-letter/retry workflow thay vì chỉ repair structured output.
- [ ] Không tự động chuyển từ local provider sang remote provider.

### Retrieval quality

- [ ] Thiết kế reranker interface độc lập provider.
- [ ] Benchmark một reranker local/cheap trên evaluation corpus trước khi chọn mặc định.
- [ ] Thêm optional cross-encoder reranking sau RRF.
- [ ] Đánh giá semantic entailment/contradiction check cho answer statements.
- [ ] Thay JSON cosine scan bằng vector index phù hợp trước khi tuyên bố scale 10.000 files/1 GB.
- [ ] Benchmark latency, memory và index-update cost; lưu receipt có version/model/config.

### Ingestion và portability còn thiếu

- [ ] Nâng polling watcher lên native filesystem notifications nếu benchmark cho thấy cần thiết.
- [ ] Thiết kế coordination cho nhiều API worker; watcher hiện chỉ an toàn trong một process.
- [ ] Hỗ trợ portable import vào database không rỗng bằng explicit merge/remap workflow.
- [ ] Không hỗ trợ overwrite phá hủy dữ liệu nếu chưa có preview và rollback semantics.

### Workspace và packaging

- [ ] Thêm workspace abstraction; hiện chỉ có một local workspace.
- [ ] Quy định workspace-scoped source identity, search, model runs, audit và deletion.
- [ ] Xác minh Windows trong CI hoặc máy thật.
- [ ] Hoàn thiện production packaging; chưa tuyên bố production support.
- [ ] Đánh giá Tauri desktop packaging sau khi local web/API workflow ổn định.

## P1 — Đánh giá bằng model và dữ liệu thật

### Real-model comparison

- [ ] Chọn ít nhất một remote/cheap model, ví dụ Qwen hoặc DeepSeek.
- [ ] Chọn ít nhất một local model qua Ollama/vLLM.
- [ ] Khóa model version, prompt version và provider configuration trong report.
- [ ] Đo extraction precision/recall cho bốn memory kinds.
- [ ] Đo grounded answer citation precision, abstention, latency và estimated cost.
- [ ] Không dùng vài demo thành công để tuyên bố chất lượng tổng quát.

### Problem corpus và pilot

- [ ] Tuyển 5 design partners hoặc engineering teams.
- [ ] Phỏng vấn 5–10 engineers.
- [ ] Thu thập tối thiểu 25 câu hỏi thật có permission và relevance judgments.
- [ ] Có ít nhất 10 câu hỏi liên quan decision thay đổi theo thời gian.
- [ ] Ghi baseline thủ công: thời gian trả lời, số nguồn phải mở và confidence.
- [ ] Chạy pilot hàng tuần và đóng băng report theo protocol trong `docs/pilot-protocol.md`.
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
- [ ] Chuẩn bị alpha release criteria và support boundary rõ ràng.

## Checklist bắt đầu phiên làm việc ngày mai

```bash
git status --short --branch
git pull --ff-only
make setup
make test
make check
make eval
```

Sau đó bắt đầu bằng ADR và vertical slice **Git repository ingestion dạng read-only** ở mục P0.

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
