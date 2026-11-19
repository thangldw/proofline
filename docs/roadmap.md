# Roadmap

## English

Items below are intentionally **not implemented**. Each needs something this repository cannot supply on its own. Nothing here is a commitment or a release date.

| Item | Why it is not built | What would unblock it |
| --- | --- | --- |
| Notion, Confluence, Jira, Linear connectors | Need external accounts, OAuth or API keys, and per-service rate-limit and permission handling. | A named service, test credentials, and a decision on where secrets live (see the `keyring` store). |
| Trusted timestamps (RFC 3161) | Needs a timestamp authority, a verifier trust policy, and an ASN.1/CMS dependency to parse tokens. | A chosen TSA, a trust configuration, and approval to add the dependency. |
| Distributing revocation lists | `verify-attestation --revocations` accepts a list you supply; nothing publishes or refreshes one. | A decision on publication and freshness rules. |
| Semantic change classification | Needs an AI provider; the verdict must stay a human decision, so it can only propose. | A provider and an evaluation set that measures false positives. |
| Real-team pilot evidence | Needs real team documents and permission to freeze them (`scripts/freeze_pilot_dataset.py` is ready). | A team willing to run the pilot. |

## Tiếng Việt

Các mục dưới đây cố ý **chưa được triển khai**: mỗi mục cần thứ mà repository này không tự cung cấp được. Không phải cam kết hay mốc phát hành.

- Connector Notion, Confluence, Jira, Linear: cần tài khoản ngoài, OAuth hoặc API key và xử lý giới hạn tốc độ, quyền theo từng dịch vụ.
- Trusted timestamp (RFC 3161): cần timestamp authority và chính sách verifier tin authority nào.
- Phân phối danh sách thu hồi khoá: `verify-attestation --revocations` nhận danh sách bạn tự cấp; chưa có kênh công bố hay làm mới.
- Phân loại thay đổi ngữ nghĩa: cần AI provider; verdict vẫn là quyết định của người nên chỉ có thể đề xuất.
- Evidence từ pilot team thật: cần tài liệu thật và quyền đóng băng chúng (`scripts/freeze_pilot_dataset.py` đã sẵn sàng).

## 日本語

以下は意図的に**未実装**です。いずれもこの repository だけでは用意できないものが必要です。約束や release 日付ではありません。

- Notion、Confluence、Jira、Linear connector: 外部 account、OAuth / API key、service ごとの rate limit と権限の扱いが必要です。
- Trusted timestamp (RFC 3161): timestamp authority と、verifier がどの authority を信頼するかの方針が必要です。
- 失効 list の配布: `verify-attestation --revocations` は利用者が用意した list を受け取りますが、公開・更新の経路はありません。
- 意味的な変更の分類: AI provider が必要で、判断は人が行うため提案のみ可能です。
- 実 team の pilot evidence: 実 document とその凍結許可が必要です (`scripts/freeze_pilot_dataset.py` は準備済み)。
