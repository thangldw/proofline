# Decision lifecycle

## English

### Two independent states

Decision status records historical governance such as `candidate`, `accepted`, or `obsolete`. Evidence-review state records whether the current source still supports the stored citations. An accepted decision can therefore be review-required without ceasing to be historically accepted.

View the [trilingual lifecycle diagram](diagrams/decision-review-lifecycle.html).

### Refresh and findings

`proofline refresh-reviews --policy proofline.toml` persists the current ledger. `proofline check-decisions` is the read-only CI projection. Each citation resolves deterministically as fresh, moved, ambiguous, changed, or deleted. Policy selects which findings fail the check; no AI provider participates.

### Review actions

- Re-anchor binds the decision to a verified current span and records immutable before/after evidence binding.
- Resolve records the review outcome without altering the source or falsifying historical evidence.
- Audit events identify actor, action, object, and before/after state.
- A portable review receipt binds one review snapshot to the exact verified Decision Evidence Package root.

### Transitive impact

`proofline check-impacts` follows only active explicit `based_on` and `implements` relations. Traversal is cycle-safe and returns a canonical shortest path. `supersedes` governs decision history but is not an impact-propagation edge. An impact finding requests review; it does not automatically change decision status.

## Tiếng Việt

### Hai state độc lập

Decision status ghi governance lịch sử như `candidate`, `accepted` hoặc `obsolete`. Evidence-review state ghi source hiện tại còn hỗ trợ citation đã lưu hay không. Vì vậy accepted decision có thể ở review-required mà vẫn giữ trạng thái historically accepted.

Xem [sơ đồ lifecycle ba ngôn ngữ](diagrams/decision-review-lifecycle.html).

### Refresh và finding

`proofline refresh-reviews --policy proofline.toml` persist ledger hiện tại. `proofline check-decisions` là projection read-only cho CI. Mỗi citation resolve xác định thành fresh, moved, ambiguous, changed hoặc deleted. Policy chọn finding nào làm check fail; AI provider không tham gia.

### Review action

- Re-anchor gắn decision với verified current span và ghi evidence binding before/after bất biến.
- Resolve ghi review outcome mà không thay source hoặc làm sai historical evidence.
- Audit event ghi actor, action, object và before/after state.
- Review receipt portable gắn một review snapshot với đúng root của Decision Evidence Package đã verify.

### Transitive impact

`proofline check-impacts` chỉ đi qua relation explicit `based_on` và `implements` đang active. Traversal cycle-safe và trả canonical shortest path. `supersedes` quản lý decision history nhưng không phải impact-propagation edge. Impact finding yêu cầu review; không tự thay decision status.

## 日本語

### 独立した二つの state

Decision status は `candidate`、`accepted`、`obsolete` など過去の governance を記録します。Evidence-review state は現在 source が保存 citation を引き続き支えるかを記録します。そのため accepted decision は historically accepted のまま review-required になり得ます。

[三言語 lifecycle diagram](diagrams/decision-review-lifecycle.html) を参照してください。

### Refresh と finding

`proofline refresh-reviews --policy proofline.toml` は現在 ledger を persist します。`proofline check-decisions` は read-only CI projection です。各 citation は決定的に fresh、moved、ambiguous、changed、deleted のいずれかに resolve されます。どの finding で check を fail させるかは policy が選び、AI provider は関与しません。

### Review action

- Re-anchor は decision を verified current span に結び付け、不変の before/after evidence binding を記録します。
- Resolve は source や historical evidence を改変せず review outcome を記録します。
- Audit event は actor、action、object、before/after state を記録します。
- Portable review receipt は review snapshot を検証済み Decision Evidence Package の正確な root に結び付けます。

### Transitive impact

`proofline check-impacts` は active で明示的な `based_on` / `implements` relation だけをたどります。Traversal は cycle-safe で canonical shortest path を返します。`supersedes` は decision history を管理しますが impact-propagation edge ではありません。Impact finding は review を要求しますが decision status を自動変更しません。
