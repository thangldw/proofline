# Local MCP server

## English

`proofline mcp` serves read-only decision checks to a local MCP client over stdio (newline-delimited JSON-RPC 2.0). It opens no network socket and never writes to the database. A remote or hosted MCP connector is a different, unimplemented design.

Register it with a client such as Claude Code or Claude Desktop:

```json
{ "mcpServers": { "proofline": { "command": "proofline", "args": ["mcp"] } } }
```

| Tool | Result |
| --- | --- |
| `check_decisions` | Approved decisions whose cited evidence is no longer unchanged: identifiers, spans, reason (`moved`, `changed`, `deleted`, `ambiguous`). |
| `check_impacts` | Decisions transitively impacted, through `based_on` and `implements`, by a decision awaiting review. |
| `list_decisions` | Decision identifiers, kind and status; optional `status` filter and `limit` (1-100). |
| `search_evidence` | Lexical search over current source versions: chunk and source identifiers with line spans. `query` (max 500 characters), `limit` (1-20). |
| `blame_location` | Approved decisions anchored at a source path (suffix, URI or title), optionally one `line` of its current version: anchor state and current line span. Titles only with `--include-titles`. |
| `why_decision` | Approved decisions matching a `question` by deterministic term matching, with citation location and health (`current`, `changed`, `moved`, `ambiguous`, `deleted`). Titles with `--include-titles`; cited text and rationale (400 characters max) with `--include-excerpts`. |
| `check_expiry` | Approved decisions past their `Review by:` date today (UTC); optional `warn_within_days`. Titles only with `--include-titles`. |
| `find_conflicts` | Candidate contradicting pairs (`min_similarity` 0-1). Shared words are title text, so they appear only with `--include-titles`. |
| `decision_graph` | Relation graph of approved decisions: node identifiers with a stale flag, edges with their kind (including `possible_conflict`); optional `include_isolated`, `include_conflicts`. Node titles only with `--include-titles`. |

Disclosure: tool results go to whatever model the client uses. Decision titles are therefore omitted unless you start the server with `proofline mcp --include-titles`. Evidence excerpts are returned by `search_evidence` only with `proofline mcp --include-excerpts` (at most 400 characters each); source titles follow `--include-titles`. Citation text from decision checks is never returned. Errors carry a code only, never database content.

Trust boundary: the server reads your local database as you. Any process that can start it can read decision identifiers and statuses. It does not authenticate callers: stdio has no transport-level identity, so rely on operating-system permissions rather than a shared secret.

### Claude Code hooks

`proofline agent-hook pre|post` makes approved decisions binding for a coding agent. Register it in `.claude/settings.json` (the Proofline plugin ships the same registration):

```json
{ "hooks": {
  "PreToolUse": [{ "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": "proofline agent-hook pre" }] }],
  "PostToolUse": [{ "matcher": "Edit|Write|MultiEdit", "hooks": [{ "type": "command", "command": "proofline agent-hook post" }] }]
} }
```

Before an edit, `pre` adds the approved decisions attached to that file (nearby `proofline-decision:` markers, cited text, applicable `Enforce:` rules) to the agent's context, labelled as quoted repository data rather than instructions, with control characters removed and size bounded. After an edit, `post` checks the `Enforce:` rules that cover the file and, on a violation, returns a `block` decision with the rule so the agent can correct the code. Both read the project's `.proofline/proofline.db` in the working directory, write nothing, stay silent when there is nothing to say or no database, and never fail the session. Decision text reaches the model, so use it only for repositories whose documents you trust.

## Tiếng Việt

`proofline mcp` phục vụ các kiểm tra decision chỉ đọc cho MCP client local qua stdio (JSON-RPC 2.0 phân tách bằng dòng mới). Nó không mở network socket và không bao giờ ghi vào database. MCP connector remote hoặc hosted là thiết kế khác, chưa được triển khai.

Đăng ký với client như Claude Code hoặc Claude Desktop bằng cấu hình JSON ở phần English.

Tool: `check_expiry` (decision quá hạn review), `find_conflicts` (cặp có thể mâu thuẫn; từ chung chỉ có với `--include-titles`), `why_decision` (decision khớp câu hỏi, kèm vị trí trích dẫn và health), `blame_location` (decision đã duyệt neo tại một file/dòng), `search_evidence` (tìm kiếm lexical, chỉ trả identifier và dòng; `--include-excerpts` mới thêm trích đoạn tối đa 400 ký tự, title theo `--include-titles`), `check_decisions` (decision đã duyệt mà evidence trích dẫn không còn unchanged), `decision_graph` (đồ thị quan hệ: id, cờ stale, loại cạnh; title chỉ với `--include-titles`), `check_impacts` (decision bị ảnh hưởng gián tiếp qua `based_on` và `implements`), `list_decisions` (identifier, kind, status; lọc `status` và `limit` 1-100).

Disclosure: kết quả tool đi tới model mà client dùng. Vì vậy title của decision bị bỏ trừ khi bạn chạy `proofline mcp --include-titles`. Citation text không bao giờ được trả về. Lỗi chỉ mang mã, không mang nội dung database.

Trust boundary: server đọc database local với quyền của bạn. Tiến trình nào khởi chạy được nó đều đọc được identifier và status của decision. Nó không xác thực caller.

### Hook cho Claude Code

`proofline agent-hook pre|post` biến decision đã duyệt thành ràng buộc với coding agent. Đăng ký trong `.claude/settings.json` bằng cấu hình ở phần English (plugin Proofline đi kèm đăng ký tương tự). Trước khi sửa, `pre` đưa vào ngữ cảnh của agent các decision gắn với file (marker `proofline-decision:` gần đó, đoạn văn bản được trích, luật `Enforce:` áp dụng), gắn nhãn là dữ liệu trích từ repository chứ không phải chỉ dẫn, đã bỏ ký tự điều khiển và giới hạn kích thước. Sau khi sửa, `post` kiểm tra các luật `Enforce:` phủ file đó và nếu vi phạm thì trả quyết định `block` kèm luật để agent sửa lại code. Cả hai đọc `.proofline/proofline.db` trong thư mục làm việc, không ghi gì, im lặng khi không có gì để nói hoặc không có database, và không bao giờ làm hỏng phiên. Nội dung decision đi tới model nên chỉ dùng cho repository có tài liệu bạn tin cậy.

## 日本語

`proofline mcp` は stdio (改行区切り JSON-RPC 2.0) 経由で、読み取り専用の decision check を local MCP client に提供します。Network socket は開かず、database へ書き込みません。Remote / hosted MCP connector は別設計で未実装です。

Claude Code や Claude Desktop などの client への登録は English 節の JSON 設定を使います。

Tool: `check_expiry` (decision quá hạn review), `find_conflicts` (cặp có thể mâu thuẫn; từ chung chỉ có với `--include-titles`), `why_decision` (decision khớp câu hỏi, kèm vị trí trích dẫn và health), `blame_location` (decision đã duyệt neo tại một file/dòng), `search_evidence` (tìm kiếm lexical, chỉ trả identifier và dòng; `--include-excerpts` mới thêm trích đoạn tối đa 400 ký tự, title theo `--include-titles`), `check_decisions` (引用 evidence が unchanged でなくなった承認済み decision)、`check_impacts` (`based_on` と `implements` を通じて間接的に影響を受ける decision)、`list_decisions` (identifier、kind、status。`status` filter と `limit` 1-100)。

Disclosure: tool の結果は client が使う model に渡ります。そのため decision の title は `proofline mcp --include-titles` で起動しない限り省かれます。Citation text は返しません。Error は code のみで database の内容を含みません。

Trust boundary: server はあなたの権限で local database を読みます。起動できる process は decision の identifier と status を読めます。Caller は認証しません。

### Claude Code の hook

`proofline agent-hook pre|post` は承認済み decision をコーディング agent への拘束力にします。English 節の設定を `.claude/settings.json` に登録します (Proofline plugin も同じ登録を同梱します)。編集前に `pre` が、そのファイルに紐づく承認済み decision (近くの `proofline-decision:` marker、引用された文、該当する `Enforce:` ルール) を、指示ではなく repository から引用したデータとして明示し、制御文字を除去してサイズを制限したうえで agent の文脈に加えます。編集後に `post` はそのファイルに適用される `Enforce:` ルールを検査し、違反があればルールとともに `block` を返して agent が code を直せるようにします。どちらも作業ディレクトリの `.proofline/proofline.db` を読むだけで何も書かず、伝えることがない場合や database がない場合は沈黙し、セッションを失敗させません。Decision の本文は model に届くため、文書を信頼できる repository でのみ使ってください。
