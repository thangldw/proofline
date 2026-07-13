# Proofline — công việc còn lại

**Cập nhật:** 2026-07-13  
**Trạng thái hiện tại:** các lát cắt P1 nội bộ đã phát hành đến `v0.11.0`; Windows, production
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
- [ ] **v0.14 Third Brain AI:** suggestion/plan có citation, human review, không autonomous write-back.
- [ ] **v0.15 Team Brain:** chỉ bắt đầu sau authentication, RBAC, organization audit và permission-aware retrieval.

Không mốc nào ở trên cho phép rich-text editor, canvas, graph database hoặc generic agent.

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
- [ ] Hoàn thiện production packaging; chưa tuyên bố production support.
- [x] Hoàn thiện embedded start/ready/stop, data-directory, migration/recovery và same-origin web
  lifecycle làm nền cho native wrapper.
- [x] Bundle reviewed web UI vào wheel và smoke-test executable đã cài để chạy local bằng một lệnh.
- [x] Đánh giá Tauri desktop packaging; ADR 0003 hoãn triển khai cho đến khi Windows, lifecycle
  API/web và production support boundary được chứng minh.

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
