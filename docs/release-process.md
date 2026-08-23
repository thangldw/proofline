# Release process

## English

### Qualification

Choose a new version; published artifacts are immutable. Align Python, runtime, web, desktop, Tauri/Cargo, lockfile, and plugin manifest versions. Add a dated `CHANGELOG.md` heading and `docs/releases/vVERSION.md`, then run:

```bash
make test
make check
make verify-package-conformance
npm run test:e2e
make audit
.venv/bin/python scripts/release_check.py --tag vVERSION
```

Build wheel and sdist from the exact clean commit, inspect both with `scripts/verify_release_artifacts.py`, and record SHA-256 digests. Do not qualify from an uncommitted tree.

### Publication

PyPI uses a project-scoped Trusted Publisher; no long-lived token belongs in the repository. Publish the exact qualified wheel/sdist, wait for both public digests, install `proofline-evidence==VERSION` without cache in a fresh environment, and run the stale-decision smoke. Create the Git tag and GitHub release only after PyPI verification.

Plugin submission is a separate external workflow. Rebuild and inspect the skills-only bundle, run bundle conformance in a clean directory, update dated submission evidence, and submit the new immutable plugin version. Never claim approval or publication until observed externally. A remote MCP connector requires a separate hosted-security design and is not part of this release path.

### Current release

As verified on 2026-08-24, PyPI reported `proofline-evidence` 2.0.1, GitHub reported release `v2.0.1` published at 2026-08-23T16:54:02Z, and the OpenAI Plugins Directory reported Proofline 2.0.1 as published. These immutable artifacts resolve to release commit `05fd080915da56944666189c424dbce2ea81de7d`.

## Tiếng Việt

### Qualification

Chọn version mới; artifact đã publish là immutable. Đồng bộ version Python, runtime, web, desktop, Tauri/Cargo, lockfile và plugin manifest. Thêm heading có ngày trong `CHANGELOG.md` cùng `docs/releases/vVERSION.md`, rồi chạy:

```bash
make test
make check
make verify-package-conformance
npm run test:e2e
make audit
.venv/bin/python scripts/release_check.py --tag vVERSION
```

Build wheel và sdist từ đúng clean commit, inspect cả hai bằng `scripts/verify_release_artifacts.py` và ghi SHA-256 digest. Không qualification từ uncommitted tree.

### Publication

PyPI dùng project-scoped Trusted Publisher; không lưu long-lived token trong repository. Publish đúng wheel/sdist đã qualified, chờ đủ hai public digest, cài `proofline-evidence==VERSION` không cache trong fresh environment và chạy stale-decision smoke. Chỉ tạo Git tag và GitHub release sau khi verify PyPI.

Plugin submission là external workflow riêng. Rebuild và inspect skills-only bundle, chạy bundle conformance trong clean directory, cập nhật dated submission evidence và submit immutable plugin version mới. Không claim approval hoặc publication trước khi quan sát bên ngoài. Remote MCP connector cần hosted-security design riêng và không thuộc release path này.

### Release hiện tại

Theo verification ngày 2026-08-24, PyPI báo `proofline-evidence` 2.0.1, GitHub báo release `v2.0.1` publish lúc 2026-08-23T16:54:02Z và OpenAI Plugins Directory báo Proofline 2.0.1 đã published. Các immutable artifact này resolve tới release commit `05fd080915da56944666189c424dbce2ea81de7d`.

## 日本語

### Qualification

新 version を選びます。公開済み artifact は immutable です。Python、runtime、web、desktop、Tauri/Cargo、lockfile、plugin manifest の version を揃え、`CHANGELOG.md` に日付付き heading、`docs/releases/vVERSION.md` を追加して実行します。

```bash
make test
make check
make verify-package-conformance
npm run test:e2e
make audit
.venv/bin/python scripts/release_check.py --tag vVERSION
```

正確な clean commit から wheel/sdist を build し、`scripts/verify_release_artifacts.py` で両方を検査し、SHA-256 digest を記録します。Uncommitted tree から qualification しません。

### Publication

PyPI は project-scoped Trusted Publisher を使い、long-lived token を repository に置きません。Qualified wheel/sdist だけを publish し、両 public digest を待ち、fresh environment に cache なしで `proofline-evidence==VERSION` を install して stale-decision smoke を実行します。PyPI verification 後にだけ Git tag と GitHub release を作ります。

Plugin submission は別の external workflow です。Skills-only bundle を再 build/inspect し、clean directory で bundle conformance を実行し、dated submission evidence を更新して新 immutable plugin version を submit します。外部観測前に approval/publication を claim しません。Remote MCP connector には別の hosted-security design が必要で、この release path には含みません。

### Current release

2026-08-24 の verification では、PyPI は `proofline-evidence` 2.0.1、GitHub は 2026-08-23T16:54:02Z 公開の `v2.0.1` release、OpenAI Plugins Directory は Proofline 2.0.1 の published status を報告しました。これらの immutable artifact は release commit `05fd080915da56944666189c424dbce2ea81de7d` に対応します。
