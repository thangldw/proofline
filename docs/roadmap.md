# Roadmap

## English

Items below are intentionally **not implemented**. Each needs something this repository cannot supply on its own. Nothing here is a commitment or a release date.

| Item | Why it is not built | What would unblock it |
| --- | --- | --- |
| Notion, Confluence, Jira, Linear connectors | Need external accounts, OAuth or API keys, and per-service rate-limit and permission handling. | A named service, test credentials, and a decision on where secrets live (see the `keyring` store). |
| Trusted timestamps (RFC 3161) | Needs a timestamp authority and a policy for which authority a verifier trusts. | A chosen TSA and a verifier trust configuration. |
| Key revocation | Needs a distribution channel for revocation lists. | A decision on publication and freshness rules. |
| Semantic change classification | Needs an AI provider; the verdict must stay a human decision, so it can only propose. | A provider and an evaluation set that measures false positives. |
| Real-team pilot evidence | Needs real team documents and permission to freeze them (`scripts/freeze_pilot_dataset.py` is ready). | A team willing to run the pilot. |
| Splitting `api.py` and `portability.py` | Tests monkeypatch `proofline.api.*`; a safe split needs those seams moved first. | A dedicated refactor with the seams made explicit. |
| Removing the mypy ratchet | 19 modules carry about 200 legacy type errors listed in `pyproject.toml`. | Fixing modules one at a time and deleting them from the list. |

## Tiếng Việt

Các mục dưới đây cố ý **chưa được triển khai**: mỗi mục cần thứ mà repository này không tự cung cấp được. Không phải cam kết hay mốc phát hành.

- Connector Notion, Confluence, Jira, Linear: cần tài khoản ngoài, OAuth hoặc API key và xử lý giới hạn tốc độ, quyền theo từng dịch vụ.
- Trusted timestamp (RFC 3161): cần timestamp authority và chính sách verifier tin authority nào.
- Key revocation: cần kênh phân phối danh sách thu hồi.
- Phân loại thay đổi ngữ nghĩa: cần AI provider; verdict vẫn là quyết định của người nên chỉ có thể đề xuất.
- Evidence từ pilot team thật: cần tài liệu thật và quyền đóng băng chúng (`scripts/freeze_pilot_dataset.py` đã sẵn sàng).
- Tách `api.py` và `portability.py`: test đang monkeypatch `proofline.api.*`; muốn tách an toàn phải chuyển các seam đó trước.
- Gỡ ratchet mypy: 19 module còn khoảng 200 lỗi kiểu cũ trong `pyproject.toml`; sửa từng module rồi xoá khỏi danh sách.

## 日本語

以下は意図的に**未実装**です。いずれもこの repository だけでは用意できないものが必要です。約束や release 日付ではありません。

- Notion、Confluence、Jira、Linear connector: 外部 account、OAuth / API key、service ごとの rate limit と権限の扱いが必要です。
- Trusted timestamp (RFC 3161): timestamp authority と、verifier がどの authority を信頼するかの方針が必要です。
- Key revocation: 失効 list の配布経路が必要です。
- 意味的な変更の分類: AI provider が必要で、判断は人が行うため提案のみ可能です。
- 実 team の pilot evidence: 実 document とその凍結許可が必要です (`scripts/freeze_pilot_dataset.py` は準備済み)。
- `api.py` と `portability.py` の分割: test が `proofline.api.*` を monkeypatch するため、先に seam の移動が必要です。
- mypy ratchet の解消: 19 module に約 200 件の既存 type error が `pyproject.toml` に列挙されています。1 module ずつ修正して list から外します。
