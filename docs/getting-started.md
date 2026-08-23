# Getting started

## English

### Requirements and install

Use Python 3.11 or newer, `uv`, Node.js 20 or newer, and npm. Repository development uses an isolated virtual environment; it does not require a global `proofline` install.

```bash
git clone https://github.com/thangldw/proofline
cd proofline
uv sync --extra dev
npm install
```

The PyPI distribution name is `proofline-evidence`; the CLI and import package are `proofline`.

### Run the stale-decision story

```bash
uv run proofline demo stale-decision
uv run proofline verify-package proofline-demo-stale-decision/evidence.zip
uv run proofline verify-review-receipt proofline-demo-stale-decision/decision-review.json
```

The demo writes only below `proofline-demo-stale-decision/` unless `--output-dir` is supplied. Reuse requires `--force`. Inspect the original and changed requirement, the decision report, the package result, and the review receipt before deleting the disposable directory.

### Run the local application

```bash
uv run proofline serve --host 127.0.0.1 --port 8765
```

Open `http://127.0.0.1:8765`. Use `--data-dir` to select local state or `--no-web` for API-only operation. The local OpenAPI document is available at `http://127.0.0.1:8765/openapi.json` while the server runs.

Next: [architecture](architecture.md), [decision lifecycle](decision-lifecycle.md), and [operations](operations.md).

## Tiếng Việt

### Yêu cầu và cài đặt

Dùng Python 3.11 trở lên, `uv`, Node.js 20 trở lên và npm. Development từ repository dùng virtual environment độc lập; không cần cài global `proofline`.

```bash
git clone https://github.com/thangldw/proofline
cd proofline
uv sync --extra dev
npm install
```

Tên PyPI distribution là `proofline-evidence`; CLI và import package là `proofline`.

### Chạy stale-decision story

```bash
uv run proofline demo stale-decision
uv run proofline verify-package proofline-demo-stale-decision/evidence.zip
uv run proofline verify-review-receipt proofline-demo-stale-decision/decision-review.json
```

Demo chỉ ghi dưới `proofline-demo-stale-decision/` trừ khi cung cấp `--output-dir`. Muốn dùng lại phải có `--force`. Hãy xem requirement gốc và bản thay đổi, decision report, package result và review receipt trước khi xoá disposable directory.

### Chạy local application

```bash
uv run proofline serve --host 127.0.0.1 --port 8765
```

Mở `http://127.0.0.1:8765`. Dùng `--data-dir` để chọn local state hoặc `--no-web` để chỉ chạy API. Local OpenAPI document có tại `http://127.0.0.1:8765/openapi.json` khi server đang chạy.

Tiếp theo: [architecture](architecture.md), [decision lifecycle](decision-lifecycle.md) và [operations](operations.md).

## 日本語

### 要件と install

Python 3.11 以上、`uv`、Node.js 20 以上、npm を使います。Repository development は独立 virtual environment を使い、global `proofline` install は不要です。

```bash
git clone https://github.com/thangldw/proofline
cd proofline
uv sync --extra dev
npm install
```

PyPI distribution 名は `proofline-evidence`、CLI と import package 名は `proofline` です。

### Stale-decision story の実行

```bash
uv run proofline demo stale-decision
uv run proofline verify-package proofline-demo-stale-decision/evidence.zip
uv run proofline verify-review-receipt proofline-demo-stale-decision/decision-review.json
```

`--output-dir` を指定しない限り、demo は `proofline-demo-stale-decision/` の下だけに書き込みます。再利用には `--force` が必要です。Disposable directory を削除する前に、元と変更後の requirement、decision report、package result、review receipt を確認します。

### Local application の実行

```bash
uv run proofline serve --host 127.0.0.1 --port 8765
```

`http://127.0.0.1:8765` を開きます。Local state の選択には `--data-dir`、API-only には `--no-web` を使います。Server 実行中の local OpenAPI document は `http://127.0.0.1:8765/openapi.json` です。

次は [architecture](architecture.md)、[decision lifecycle](decision-lifecycle.md)、[operations](operations.md) を参照してください。
