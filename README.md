# Proofline

[English](#english) · [Tiếng Việt](#tiếng-việt) · [日本語](#日本語)

## English

Proofline is a local-first engineering decision memory that binds decisions to immutable source versions and exact citation spans. When a requirement changes, deterministic checks mark the affected evidence for review without rewriting the historical decision.

### Five-minute path

The PyPI distribution is `proofline-evidence`; the installed CLI and Python package are `proofline`.

```bash
git clone https://github.com/thangldw/proofline
cd proofline
uv sync --extra dev
uv run proofline demo stale-decision
```

The demo creates a disposable workspace, changes a cited requirement, reports the citation as stale, moves the current review state to review-required, and verifies the exported evidence package from its root hash.

### Implemented boundary

- Deterministic local ingest into SQLite/FTS with immutable source versions and exact spans.
- Historical decision status separated from current evidence-review state.
- Cycle-safe transitive impact over explicit `based_on` and `implements` relations.
- Portable Decision Evidence Packages, decision-review receipts, and optional Ed25519 attestations.
- Local CLI, API, web UI, and desktop shell; integrity-critical verification does not require an AI provider.

A valid package root proves integrity, not authenticity. A valid Ed25519 signature proves matching private-key control relative to the verifier's trusted public key; it does not prove legal identity, trusted time, authorization, or revocation status.

Published scale figures are synthetic regression evidence, not team or hosted-production benchmarks. Current scope is one local user. Hosted sync, shared workspaces, OAuth, organization identity, trusted timestamps, key revocation, and remote MCP are not implemented.

### Documentation and releases

Start with the [documentation hub](docs/README.md), [getting started](docs/getting-started.md), [architecture](docs/architecture.md), [decision lifecycle](docs/decision-lifecycle.md), [evidence package formats](docs/evidence-packages.md), [operations](docs/operations.md), and [v2.0.0 release notes](docs/releases/v2.0.0.md).

Proofline is also packaged as a local skills plugin. The [OpenAI plugin submission record](docs/submission/openai-plugin.md) separates repository facts from dated external publication observations. The recorded [OpenAI Plugins Directory URL](https://chatgpt.com/plugins/plugins_6a6efdf2ccbc81919ebb4cb01805ebaa) does not imply that the repository can independently confirm the currently public version; this project does not claim a hosted connector.

See [privacy](PRIVACY.md), [security](SECURITY.md), [support](SUPPORT.md), [terms](TERMS.md), [contributing](CONTRIBUTING.md), and the [MIT License](LICENSE).

## Tiếng Việt

Proofline là bộ nhớ quyết định kỹ thuật local-first, liên kết decision với phiên bản nguồn bất biến và exact citation span. Khi requirement thay đổi, kiểm tra xác định đánh dấu evidence bị ảnh hưởng để review mà không viết lại decision lịch sử.

### Luồng dưới năm phút

PyPI distribution là `proofline-evidence`; CLI và Python package sau khi cài đặt là `proofline`.

```bash
git clone https://github.com/thangldw/proofline
cd proofline
uv sync --extra dev
uv run proofline demo stale-decision
```

Demo tạo workspace dùng một lần, sửa requirement đã được trích dẫn, báo citation stale, chuyển review state hiện tại sang review-required và xác minh evidence package đã export bằng root hash.

### Phạm vi đã triển khai

- Ingest local xác định vào SQLite/FTS với phiên bản nguồn bất biến và exact span.
- Tách historical decision status khỏi evidence-review state hiện tại.
- Transitive impact cycle-safe trên quan hệ explicit `based_on` và `implements`.
- Decision Evidence Package portable, decision-review receipt và attestation Ed25519 tùy chọn.
- CLI, API, web UI và desktop shell local; đường xác minh integrity quan trọng không cần AI provider.

Root package hợp lệ chứng minh integrity, không chứng minh authenticity. Signature Ed25519 hợp lệ chứng minh quyền kiểm soát private key tương ứng với trusted public key do verifier cung cấp; nó không chứng minh legal identity, trusted time, authorization hoặc revocation status.

Các số liệu scale đã công bố là bằng chứng hồi quy synthetic, không phải benchmark team hoặc hosted production. Phạm vi hiện tại là một người dùng local. Hosted sync, shared workspace, OAuth, organization identity, trusted timestamp, key revocation và remote MCP chưa được triển khai.

### Tài liệu và release

Bắt đầu từ [documentation hub](docs/README.md), [getting started](docs/getting-started.md), [architecture](docs/architecture.md), [decision lifecycle](docs/decision-lifecycle.md), [định dạng evidence package](docs/evidence-packages.md), [operations](docs/operations.md) và [release note v2.0.0](docs/releases/v2.0.0.md).

Proofline cũng được đóng gói thành local skills plugin. [Hồ sơ submission OpenAI plugin](docs/submission/openai-plugin.md) tách repository fact khỏi quan sát external publication có ngày. [URL OpenAI Plugins Directory](https://chatgpt.com/plugins/plugins_6a6efdf2ccbc81919ebb4cb01805ebaa) đã ghi không có nghĩa repository có thể tự xác nhận version đang public; project này không claim hosted connector.

Xem [privacy](PRIVACY.md), [security](SECURITY.md), [support](SUPPORT.md), [terms](TERMS.md), [contributing](CONTRIBUTING.md) và [MIT License](LICENSE).

## 日本語

Proofline は、decision を不変の source version と正確な citation span に結び付ける local-first の engineering decision memory です。Requirement が変わると、決定的検査が影響を受けた evidence を review 対象にし、過去の decision 自体は書き換えません。

### 五分以内の操作

PyPI distribution 名は `proofline-evidence`、インストールされる CLI と Python package 名は `proofline` です。

```bash
git clone https://github.com/thangldw/proofline
cd proofline
uv sync --extra dev
uv run proofline demo stale-decision
```

Demo は使い捨て workspace を作成し、引用済み requirement を変更し、citation を stale と報告し、現在の review state を review-required に移し、export した evidence package を root hash から検証します。

### 実装済みの境界

- 不変 source version と exact span を持つ SQLite/FTS への決定的 local ingest。
- 過去の decision status と現在の evidence-review state の分離。
- 明示的な `based_on` / `implements` 関係に対する cycle-safe な transitive impact。
- Portable Decision Evidence Package、decision-review receipt、任意の Ed25519 attestation。
- Local CLI、API、web UI、desktop shell。Integrity-critical verification は AI provider を必要としません。

有効な package root が証明するのは integrity であり authenticity ではありません。有効な Ed25519 signature は verifier が信頼する public key に対応する private key の制御を証明しますが、legal identity、trusted time、authorization、revocation status は証明しません。

公開 scale 数値は synthetic regression evidence であり、team または hosted production benchmark ではありません。現在の対象は一人の local user です。Hosted sync、shared workspace、OAuth、organization identity、trusted timestamp、key revocation、remote MCP は未実装です。

### 文書と release

[Documentation hub](docs/README.md)、[getting started](docs/getting-started.md)、[architecture](docs/architecture.md)、[decision lifecycle](docs/decision-lifecycle.md)、[evidence package format](docs/evidence-packages.md)、[operations](docs/operations.md)、[v2.0.0 release note](docs/releases/v2.0.0.md) を参照してください。

Proofline は local skills plugin としても packaging されています。[OpenAI plugin submission record](docs/submission/openai-plugin.md) は repository fact と日付付き external publication observation を分離します。記録済み [OpenAI Plugins Directory URL](https://chatgpt.com/plugins/plugins_6a6efdf2ccbc81919ebb4cb01805ebaa) は、repository が現在の public version を独立確認できることを意味しません。この project は hosted connector を提供すると主張しません。

[Privacy](PRIVACY.md)、[security](SECURITY.md)、[support](SUPPORT.md)、[terms](TERMS.md)、[contributing](CONTRIBUTING.md)、[MIT License](LICENSE) も参照してください。
