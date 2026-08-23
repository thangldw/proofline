# Contributing to Proofline

## English

### Workflow

Use Python 3.11 or newer and Node.js 20 or newer. Create a focused branch or worktree, then install the exact development surface:

```bash
uv sync --extra dev
npm install
```

For a feature or defect, add a failing regression first, make the smallest contract-preserving change, and run the targeted test before full gates. Do not rewrite immutable schemas/vectors, weaken fail-closed behavior, or change exact-span cardinality without an approved specification change.

```bash
make test
make check
make verify-package-conformance
make audit
npm run test:e2e
```

Evidence in documentation or release notes must identify the command, artifact/version, environment limitation, and observation date. Label synthetic results as synthetic. Never present design intent as shipped behavior.

Report vulnerabilities through [GitHub Security Advisories](https://github.com/thangldw/proofline/security/advisories/new), not a public issue. Releases are immutable: use a new version for any published artifact change and follow the [release process](docs/release-process.md).

## Tiếng Việt

### Quy trình

Dùng Python 3.11 trở lên và Node.js 20 trở lên. Tạo branch hoặc worktree tập trung, sau đó cài đúng development surface:

```bash
uv sync --extra dev
npm install
```

Với feature hoặc defect, thêm regression đang fail trước, thực hiện thay đổi nhỏ nhất giữ nguyên contract và chạy targeted test trước full gate. Không viết lại schema/vector bất biến, làm yếu hành vi fail-closed hoặc thay đổi exact-span cardinality nếu chưa có spec change được duyệt.

```bash
make test
make check
make verify-package-conformance
make audit
npm run test:e2e
```

Evidence trong tài liệu hoặc release note phải nêu command, artifact/version, giới hạn môi trường và ngày quan sát. Kết quả synthetic phải ghi rõ synthetic. Không trình bày design intent như behavior đã phát hành.

Báo vulnerability qua [GitHub Security Advisories](https://github.com/thangldw/proofline/security/advisories/new), không dùng public issue. Release là immutable: mọi thay đổi artifact đã publish phải dùng version mới và tuân theo [release process](docs/release-process.md).

## 日本語

### Workflow

Python 3.11 以上と Node.js 20 以上を使用します。範囲を限定した branch または worktree を作り、正確な development surface をインストールします。

```bash
uv sync --extra dev
npm install
```

Feature または defect では、まず失敗する regression を追加し、contract を維持する最小変更を行い、full gate の前に targeted test を実行します。承認済み specification change なしで immutable schema/vector を書き換えたり、fail-closed behavior を弱めたり、exact-span cardinality を変えたりしません。

```bash
make test
make check
make verify-package-conformance
make audit
npm run test:e2e
```

Documentation または release note の evidence には command、artifact/version、環境上の制約、観測日を記載します。Synthetic result は synthetic と明記し、design intent を出荷済み behavior として示しません。

Vulnerability は public issue ではなく [GitHub Security Advisories](https://github.com/thangldw/proofline/security/advisories/new) で報告してください。Release は immutable です。公開済み artifact の変更には新 version を使い、[release process](docs/release-process.md) に従います。
