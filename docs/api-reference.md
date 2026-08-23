# API reference

## English

Start the local API with `proofline serve --host 127.0.0.1 --port 8765 --no-web`. The exhaustive machine-readable contract is `http://127.0.0.1:8765/openapi.json` while the server runs; interactive docs are local only.

Most domain routes accept `X-Proofline-Workspace-ID`; omission selects the committed default workspace. This header scopes local records, not authenticated tenancy. The API has no OAuth or remote authorization layer. Routes in the table are relative to `/api/v1`.

| Surface | Representative routes | Mutation boundary |
|---|---|---|
| Workspaces/overview | `POST /workspaces`, `GET /workspaces`, `GET /overview` | Workspace creation mutates local SQLite. |
| Sources/ingest | `POST /sources`, `POST /folder-scans`, `POST /git-repositories`, `GET /sources`, `GET /sources/{id}/versions`, `DELETE /sources/{id}` | Ingest/version/delete mutate local state and can read explicitly selected files. |
| Notes/studio/study | `/notes`, `/studio-artifacts`, `/study-cards` | Create/update/delete operations mutate local state; downloads return generated local artifacts. |
| Memories/decisions | `/memories`, `/decisions`, `/decision-relations`, `/decisions/{id}/timeline` | PATCH/POST operations are audited; relation creation can mark a superseded decision obsolete. |
| Review/impact | `/decision-health/overview`, `/decision-reviews`, `/decision-reviews/refresh`, `/decision-impacts`, `/decision-impacts/summary`, `/decision-impacts/snapshot` | Refresh, patch, re-anchor, and resolve mutate the review ledger; impact GET routes are read-only. |
| Retrieval/model | `/search`, `/answers`, `/model/*`, `/action-proposals` | Provider calls occur only on configured generation/embedding paths; proposals remain candidates until reviewed. |
| Audit/jobs | `/audit-events`, `/jobs`, `/model/runs` | Read routes expose local execution metadata; retry routes create new work. |

`POST /sources` supports `Idempotency-Key` and returns `X-Proofline-Job-ID`. Provider-backed extraction/answer paths can return `X-Proofline-Model-Run-ID`. Inspect OpenAPI for exact request/response schemas and status codes before integration. Bind only to loopback unless an independent deployment adds authentication and transport controls.

## Tiếng Việt

Khởi động local API bằng `proofline serve --host 127.0.0.1 --port 8765 --no-web`. Contract machine-readable đầy đủ là `http://127.0.0.1:8765/openapi.json` khi server chạy; interactive docs chỉ ở local.

Phần lớn domain route nhận `X-Proofline-Workspace-ID`; nếu bỏ qua sẽ chọn default workspace đã commit. Header này scope local record, không phải authenticated tenancy. API không có OAuth hoặc remote authorization layer. Route trong bảng là relative với `/api/v1`.

| Surface | Route đại diện | Mutation boundary |
|---|---|---|
| Workspace/overview | `POST /workspaces`, `GET /workspaces`, `GET /overview` | Tạo workspace mutate SQLite local. |
| Source/ingest | `POST /sources`, `POST /folder-scans`, `POST /git-repositories`, `GET /sources`, `GET /sources/{id}/versions`, `DELETE /sources/{id}` | Ingest/version/delete mutate local state và có thể đọc file được chọn explicit. |
| Note/studio/study | `/notes`, `/studio-artifacts`, `/study-cards` | Create/update/delete mutate local state; download trả generated local artifact. |
| Memory/decision | `/memories`, `/decisions`, `/decision-relations`, `/decisions/{id}/timeline` | PATCH/POST được audit; tạo relation có thể đánh obsolete decision bị supersede. |
| Review/impact | `/decision-health/overview`, `/decision-reviews`, `/decision-reviews/refresh`, `/decision-impacts`, `/decision-impacts/summary`, `/decision-impacts/snapshot` | Refresh, patch, re-anchor và resolve mutate review ledger; impact GET route read-only. |
| Retrieval/model | `/search`, `/answers`, `/model/*`, `/action-proposals` | Provider call chỉ xảy ra trên generation/embedding path đã cấu hình; proposal giữ candidate đến khi review. |
| Audit/job | `/audit-events`, `/jobs`, `/model/runs` | Read route cung cấp local execution metadata; retry route tạo work mới. |

`POST /sources` hỗ trợ `Idempotency-Key` và trả `X-Proofline-Job-ID`. Path extraction/answer dùng provider có thể trả `X-Proofline-Model-Run-ID`. Xem OpenAPI để biết chính xác request/response schema và status code trước integration. Chỉ bind loopback trừ khi deployment độc lập bổ sung authentication và transport control.

## 日本語

Local API は `proofline serve --host 127.0.0.1 --port 8765 --no-web` で起動します。Server 実行中の完全な machine-readable contract は `http://127.0.0.1:8765/openapi.json` で、interactive docs も local 限定です。

多くの domain route は `X-Proofline-Workspace-ID` を受け取り、省略時は committed default workspace を選びます。この header は local record を scope するもので authenticated tenancy ではありません。API に OAuth または remote authorization layer はありません。表の route は `/api/v1` からの相対 path です。

| Surface | 代表 route | Mutation boundary |
|---|---|---|
| Workspace/overview | `POST /workspaces`, `GET /workspaces`, `GET /overview` | Workspace creation は local SQLite を変更します。 |
| Source/ingest | `POST /sources`, `POST /folder-scans`, `POST /git-repositories`, `GET /sources`, `GET /sources/{id}/versions`, `DELETE /sources/{id}` | Ingest/version/delete は local state を変更し、明示選択 file を読み得ます。 |
| Note/studio/study | `/notes`, `/studio-artifacts`, `/study-cards` | Create/update/delete は local state を変更し、download は generated local artifact を返します。 |
| Memory/decision | `/memories`, `/decisions`, `/decision-relations`, `/decisions/{id}/timeline` | PATCH/POST は audit され、relation creation は superseded decision を obsolete にし得ます。 |
| Review/impact | `/decision-health/overview`, `/decision-reviews`, `/decision-reviews/refresh`, `/decision-impacts`, `/decision-impacts/summary`, `/decision-impacts/snapshot` | Refresh、patch、re-anchor、resolve は review ledger を変更し、impact GET route は read-only です。 |
| Retrieval/model | `/search`, `/answers`, `/model/*`, `/action-proposals` | Provider call は設定済み generation/embedding path だけで発生し、proposal は review まで candidate です。 |
| Audit/job | `/audit-events`, `/jobs`, `/model/runs` | Read route は local execution metadata を返し、retry route は新 work を作ります。 |

`POST /sources` は `Idempotency-Key` を支援し、`X-Proofline-Job-ID` を返します。Provider-backed extraction/answer path は `X-Proofline-Model-Run-ID` を返し得ます。Integration 前に OpenAPI で正確な request/response schema と status code を確認してください。独立 deployment が authentication と transport control を追加しない限り、loopback だけに bind します。
