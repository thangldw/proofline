# Pull-request gate

## English

Fail a pull request when a document that an approved decision cites has changed that exact evidence. The gate is deterministic, needs no AI provider and no hosted service.

1. Approve decisions locally, then export a snapshot into the repository: `proofline export --output .proofline/decisions.json`. Commit it.
2. Note the `file://` URI root your documents had when decisions were approved (the folder's absolute path, for example `file:///Users/me/repo/docs`). Sources are matched by URI, so CI must reuse it.
3. Add the workflow:

```yaml
name: decision-check
on: pull_request
permissions:
  contents: read
jobs:
  decisions:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          persist-credentials: false
      - uses: thangldw/proofline@v2.10.0
        with:
          path: docs
          snapshot: .proofline/decisions.json
          uri-root: file:///Users/me/repo/docs
```

The action runs `proofline import`, `proofline sync`, and `proofline check-decisions`, writes a SARIF file, and exits non-zero when findings match the `fail_on` list in `proofline.toml`. Pin the action to a full commit SHA in production.

Two more optional checks run in the same step and fail it independently: `check-expiry: "true"` fails when an approved decision is past its `Review by:` date, and `code-refs: "src docs"` (space-separated paths in your checkout) fails when a `proofline-decision: <id>` marker points at a missing, unapproved or stale decision.

Two further inputs need `proofline-version` 2.10.0 or newer: `enforce: "true"` fails when code violates an `Enforce:` rule of an approved decision (`proofline check-enforcement` in the checked-out workspace), and `code-context: "true"` appends, on pull requests, the decisions touched by the change to the job summary (informational; it needs `actions/checkout` with `fetch-depth: 0`). `undocumented: "true"` lists added dependencies and infrastructure files that no approved decision mentions. `ledger: .proofline/ledger.jsonl` compares the current health with the committed ledger at the base ref and reports the stale-rate change, newly stale and recovered decisions in the job summary.

Optional pull-request comment: set `comment: "true"` and grant `pull-requests: write` to have the action create or update one content-free comment (decision ids, line ranges, reasons, downstream impact counts; no titles or quotes). It only runs on `pull_request` events and is skipped otherwise.

```yaml
permissions:
  contents: read
  pull-requests: write
...
      - uses: thangldw/proofline@v2.10.0
        with:
          comment: "true"
          # path, snapshot, uri-root as above
```

Scale: on a synthetic workspace of 10,000 Markdown files (Apple M-series, Python 3.15), the first `proofline sync` took about 51 s (roughly 195 files/s, one durable ingestion job per file), a re-sync with nothing changed about 2.2 s, a re-sync with 1% changed about 2.8 s, and `check-decisions` about 0.4 s. Reproduce with `python scripts/benchmark_workspace.py --documents 10000`.

Trust boundary: the snapshot is an ordinary repository file. Anyone who can change it can change which decisions exist, so protect the branch and review snapshot diffs. The check proves a cited quote is absent from the current document; it does not judge whether the change is acceptable.

## Tiếng Việt

Làm fail pull request khi tài liệu mà decision đã duyệt trích dẫn bị đổi đúng đoạn evidence đó. Gate xác định, không cần AI provider và không cần dịch vụ hosted.

1. Duyệt decision ở local rồi export snapshot vào repository: `proofline export --output .proofline/decisions.json`. Commit file này.
2. Ghi lại `file://` URI root của thư mục tài liệu lúc duyệt decision (đường dẫn tuyệt đối, ví dụ `file:///Users/me/repo/docs`). Source được khớp theo URI nên CI phải dùng lại đúng giá trị này.
3. Thêm workflow như ví dụ ở phần English.

Action chạy `proofline import`, `proofline sync` và `proofline check-decisions`, ghi file SARIF và thoát khác 0 khi finding khớp danh sách `fail_on` trong `proofline.toml`. Ở production hãy pin action theo full commit SHA.

Hai kiểm tra tùy chọn khác chạy trong cùng step và làm step fail độc lập: `check-expiry: "true"` fail khi decision đã duyệt quá hạn `Review by:`, và `code-refs: "src docs"` (các đường dẫn cách nhau bởi dấu cách) fail khi marker `proofline-decision: <id>` trỏ tới decision không tồn tại, chưa duyệt hoặc stale.

Hai input nữa cần `proofline-version` 2.10.0 trở lên: `enforce: "true"` fail khi code vi phạm luật `Enforce:` của decision đã duyệt (`proofline check-enforcement` trong workspace đã checkout), và `code-context: "true"` thêm vào job summary, trên pull request, các decision bị thay đổi chạm tới (chỉ thông tin; cần `actions/checkout` với `fetch-depth: 0`). `undocumented: "true"` liệt kê dependency và file hạ tầng mới thêm mà không decision đã duyệt nào nhắc tới. `ledger: .proofline/ledger.jsonl` so sánh health hiện tại với ledger đã commit ở base ref và báo thay đổi tỉ lệ stale, decision mới stale và đã phục hồi trong job summary.

Comment tùy chọn: đặt `comment: "true"` và cấp `pull-requests: write` để action tạo hoặc cập nhật một comment không chứa nội dung (id decision, dải dòng, lý do, số decision bị ảnh hưởng; không có title hay quote). Chỉ chạy với sự kiện `pull_request`.

Quy mô: với 10.000 file Markdown tổng hợp, `proofline sync` lần đầu mất khoảng 51 s, re-sync không đổi khoảng 2,2 s, re-sync đổi 1% khoảng 2,8 s, `check-decisions` khoảng 0,4 s. Tái hiện bằng `python scripts/benchmark_workspace.py --documents 10000`.

Trust boundary: snapshot chỉ là file thường trong repository. Ai sửa được nó thì đổi được tập decision, nên cần bảo vệ branch và review diff của snapshot. Check chỉ chứng minh quote được trích không còn trong tài liệu hiện tại; nó không đánh giá thay đổi đó có chấp nhận được không.

## 日本語

承認済み decision が引用する document の evidence 箇所が変更された pull request を fail させます。Gate は決定的で、AI provider も hosted service も不要です。

1. Local で decision を承認し、snapshot を repository に export して commit します: `proofline export --output .proofline/decisions.json`。
2. Decision 承認時に document folder が持っていた `file://` URI root (絶対 path、例 `file:///Users/me/repo/docs`) を控えます。Source は URI で照合されるため、CI でも同じ値が必要です。
3. English 節の workflow を追加します。

Action は `proofline import`、`proofline sync`、`proofline check-decisions` を実行し、SARIF file を出力し、`proofline.toml` の `fail_on` に該当する finding があれば non-zero で終了します。Production では action を full commit SHA に pin してください。

任意の 2 つの検査が同じ step で独立して失敗します: `check-expiry: "true"` は承認済み decision が `Review by:` を過ぎると失敗し、`code-refs: "src docs"` (空白区切りの path) は `proofline-decision: <id>` marker が存在しない・未承認・stale の decision を指すと失敗します。

さらに 2 つの input は `proofline-version` 2.10.0 以降が必要です: `enforce: "true"` は code が承認済み decision の `Enforce:` ルールに違反すると失敗し (checkout した workspace で `proofline check-enforcement`)、`code-context: "true"` は pull request で変更が触れた decision を job summary に追記します (情報のみ。`fetch-depth: 0` の `actions/checkout` が必要です)。`undocumented: "true"` は追加された dependency とインフラのファイルのうち、承認済み decision が言及していないものを一覧にします。`ledger: .proofline/ledger.jsonl` は現在の health を base ref にコミットされた ledger と比較し、stale 率の変化、新たに stale になった decision と回復した decision を job summary に出します。

Comment (任意): `comment: "true"` を設定し `pull-requests: write` を付与すると、内容を含まない comment (decision id、行範囲、理由、影響件数。title や quote なし) を 1 件作成または更新します。`pull_request` event でのみ動作します。

規模: 合成 Markdown 10,000 file で、初回 `proofline sync` は約 51 秒、変更なしの再 sync は約 2.2 秒、1% 変更の再 sync は約 2.8 秒、`check-decisions` は約 0.4 秒でした。`python scripts/benchmark_workspace.py --documents 10000` で再現できます。

Trust boundary: snapshot は通常の repository file です。変更できる人は decision の集合を変えられるため、branch を保護し snapshot の diff を review してください。この check は引用 quote が現在の document に存在しないことを示すだけで、変更が許容できるかは判断しません。
