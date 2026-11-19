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
      - uses: thangldw/proofline@v2.1.2
        with:
          path: docs
          snapshot: .proofline/decisions.json
          uri-root: file:///Users/me/repo/docs
```

The action runs `proofline import`, `proofline sync`, and `proofline check-decisions`, writes a SARIF file, and exits non-zero when findings match the `fail_on` list in `proofline.toml`. Pin the action to a full commit SHA in production.

Trust boundary: the snapshot is an ordinary repository file. Anyone who can change it can change which decisions exist, so protect the branch and review snapshot diffs. The check proves a cited quote is absent from the current document; it does not judge whether the change is acceptable.

## Tiếng Việt

Làm fail pull request khi tài liệu mà decision đã duyệt trích dẫn bị đổi đúng đoạn evidence đó. Gate xác định, không cần AI provider và không cần dịch vụ hosted.

1. Duyệt decision ở local rồi export snapshot vào repository: `proofline export --output .proofline/decisions.json`. Commit file này.
2. Ghi lại `file://` URI root của thư mục tài liệu lúc duyệt decision (đường dẫn tuyệt đối, ví dụ `file:///Users/me/repo/docs`). Source được khớp theo URI nên CI phải dùng lại đúng giá trị này.
3. Thêm workflow như ví dụ ở phần English.

Action chạy `proofline import`, `proofline sync` và `proofline check-decisions`, ghi file SARIF và thoát khác 0 khi finding khớp danh sách `fail_on` trong `proofline.toml`. Ở production hãy pin action theo full commit SHA.

Trust boundary: snapshot chỉ là file thường trong repository. Ai sửa được nó thì đổi được tập decision, nên cần bảo vệ branch và review diff của snapshot. Check chỉ chứng minh quote được trích không còn trong tài liệu hiện tại; nó không đánh giá thay đổi đó có chấp nhận được không.

## 日本語

承認済み decision が引用する document の evidence 箇所が変更された pull request を fail させます。Gate は決定的で、AI provider も hosted service も不要です。

1. Local で decision を承認し、snapshot を repository に export して commit します: `proofline export --output .proofline/decisions.json`。
2. Decision 承認時に document folder が持っていた `file://` URI root (絶対 path、例 `file:///Users/me/repo/docs`) を控えます。Source は URI で照合されるため、CI でも同じ値が必要です。
3. English 節の workflow を追加します。

Action は `proofline import`、`proofline sync`、`proofline check-decisions` を実行し、SARIF file を出力し、`proofline.toml` の `fail_on` に該当する finding があれば non-zero で終了します。Production では action を full commit SHA に pin してください。

Trust boundary: snapshot は通常の repository file です。変更できる人は decision の集合を変えられるため、branch を保護し snapshot の diff を review してください。この check は引用 quote が現在の document に存在しないことを示すだけで、変更が許容できるかは判断しません。
