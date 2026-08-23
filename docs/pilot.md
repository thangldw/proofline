# Real pilot evidence

## English

### Evidence boundary

Proofline implements a fail-closed path for collecting, freezing, and aggregating a private team
pilot. The repository does not contain a real pilot result. A generated manifest proves only the
identity of the five input files; it does not prove adoption, usefulness, willingness to pay,
security qualification, or production performance.

### Required private inputs

Create a private directory with these exact names:

- `questions.jsonl`
- `attempts.csv`
- `citations.csv`
- `weekly-usage.csv`
- `commercial-signals.csv`

The field shapes are defined by the files in `evals/pilot/`. Replace every example row before
collection. The freezer rejects empty files, dataset-version mismatches, `synthetic_example`,
`blank_template`, and identifiers prefixed with `synthetic-` or `synthetic_`. Use consented,
sanitized identifiers and keep the directory outside the repository.

### Freeze, analyze, and review

```bash
.venv/bin/python scripts/freeze_pilot_dataset.py /absolute/private/pilot \
  --dataset-version private-pilot-v1
.venv/bin/python scripts/analyze_pilot.py /absolute/private/pilot \
  --output /absolute/private/pilot-analysis.json
```

The freezer writes `manifest.json` atomically with mode `0600` on POSIX hosts, an explicit dataset
version, and a SHA-256 digest for every input. It refuses overwrite unless `--force` is explicit.
The analyzer recomputes all hashes before calculating aggregates and fails if the frozen inputs
changed.

The analysis remains `aggregate_analysis_unsigned` with `awaiting_owner_signoff`. Dataset owners
must review the private records, consent scope, exclusions, citation adjudication, and platform or
security receipts before treating the aggregates as pilot evidence. The separate
`security-platform.v1.template.csv` captures that review; its hard gate remains open until real
receipts exist.

`simulate_pilot.py` is only a credential-free regression exercise. Its output must never be merged
with or described as real pilot evidence.

## Tiếng Việt

### Ranh giới evidence

Proofline triển khai luồng fail-closed để thu thập, freeze và tổng hợp pilot team private.
Repository không chứa kết quả pilot thật. Manifest được tạo chỉ chứng minh identity của năm input
file; nó không chứng minh adoption, usefulness, willingness to pay, security qualification hoặc
production performance.

### Input private bắt buộc

Tạo một private directory với đúng các tên sau:

- `questions.jsonl`
- `attempts.csv`
- `citations.csv`
- `weekly-usage.csv`
- `commercial-signals.csv`

Các file trong `evals/pilot/` định nghĩa field shape. Phải thay mọi example row trước khi thu thập.
Freezer từ chối file rỗng, dataset version không khớp, `synthetic_example`, `blank_template` và
identifier bắt đầu bằng `synthetic-` hoặc `synthetic_`. Chỉ dùng identifier đã sanitize, có consent
và giữ directory ngoài repository.

### Freeze, analyze và review

```bash
.venv/bin/python scripts/freeze_pilot_dataset.py /absolute/private/pilot \
  --dataset-version private-pilot-v1
.venv/bin/python scripts/analyze_pilot.py /absolute/private/pilot \
  --output /absolute/private/pilot-analysis.json
```

Freezer ghi atomic `manifest.json` với mode `0600` trên POSIX host, dataset version explicit và
SHA-256 cho từng input. Nó không overwrite nếu thiếu `--force`. Analyzer tính lại toàn bộ hash
trước khi tính aggregate và fail nếu frozen input đã thay đổi.

Analysis vẫn mang trạng thái `aggregate_analysis_unsigned` và `awaiting_owner_signoff`. Dataset
owner phải review private record, consent scope, exclusion, citation adjudication và platform hoặc
security receipt trước khi coi aggregate là pilot evidence. File
`security-platform.v1.template.csv` dùng cho phần review riêng này; hard gate vẫn open cho tới khi
có receipt thật.

`simulate_pilot.py` chỉ là credential-free regression exercise. Không được trộn hoặc mô tả output
của nó như pilot evidence thật.

## 日本語

### Evidence boundary

Proofline は private team pilot を収集、freeze、aggregate する fail-closed path を実装します。
Repository には real pilot result は含まれていません。生成された manifest が証明するのは
五つの input file の identity だけであり、adoption、usefulness、willingness to pay、security
qualification、production performance は証明しません。

### 必須 private input

次の exact name を持つ private directory を作成します：

- `questions.jsonl`
- `attempts.csv`
- `citations.csv`
- `weekly-usage.csv`
- `commercial-signals.csv`

Field shape は `evals/pilot/` の file で定義されています。収集前にすべての example row を
置換します。Freezer は empty file、dataset-version mismatch、`synthetic_example`、
`blank_template`、`synthetic-` または `synthetic_` で始まる identifier を拒否します。
Consent 済みで sanitized な identifier のみを使用し、directory は repository 外に保管します。

### Freeze、analyze、review

```bash
.venv/bin/python scripts/freeze_pilot_dataset.py /absolute/private/pilot \
  --dataset-version private-pilot-v1
.venv/bin/python scripts/analyze_pilot.py /absolute/private/pilot \
  --output /absolute/private/pilot-analysis.json
```

Freezer は POSIX host で mode `0600` の `manifest.json` を atomic に書き込み、explicit
dataset version と各 input の SHA-256 digest を記録します。`--force` がない overwrite は
拒否します。Analyzer は aggregate 計算前に全 hash を再計算し、frozen input の変更時には
失敗します。

Analysis の状態は `aggregate_analysis_unsigned` と `awaiting_owner_signoff` のままです。
Aggregate を pilot evidence として扱う前に、dataset owner が private record、consent scope、
exclusion、citation adjudication、platform/security receipt を確認する必要があります。
別の `security-platform.v1.template.csv` がこの review を記録し、real receipt が存在するまで
hard gate は open のままです。

`simulate_pilot.py` は credential-free regression exercise にすぎません。その output を real
pilot evidence と混在させたり、そのように説明したりしてはいけません。
