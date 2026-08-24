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

As verified on 2026-08-24, PyPI, GitHub Releases, and the OpenAI Plugins Directory reported Proofline 2.0.2 as published. The Git tag resolves to release commit `5328eba3cd907db1190ce2a3be7a5f96ae5b67be`. Public PyPI SHA-256 digests are `f5e256f8a91a8c61f80e6b588a5bfd102990972d01fe5db6628b378812f45474` for the wheel and `59e6f155912a66cffb88493f5e114928c8aa71ef76fe4cab39891bc8feda28bd` for the sdist. The submitted plugin ZIP SHA-256 is `c6e8e83ba66e78811dcd6d99011d6454abb367969abf77ca7dbbd1803df8360`, and submission `appsub_6a8ba7cb85dc81919f961b5ca9a9f62d` was observed as published.

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

Theo verification ngày 2026-08-24, PyPI, GitHub Releases và OpenAI Plugins Directory đều báo Proofline 2.0.2 đã published. Git tag resolve tới release commit `5328eba3cd907db1190ce2a3be7a5f96ae5b67be`. Public PyPI SHA-256 là `f5e256f8a91a8c61f80e6b588a5bfd102990972d01fe5db6628b378812f45474` cho wheel và `59e6f155912a66cffb88493f5e114928c8aa71ef76fe4cab39891bc8feda28bd` cho sdist. Submitted plugin ZIP SHA-256 là `c6e8e83ba66e78811dcd6d99011d6454abb367969abf77ca7dbbd1803df8360`; submission `appsub_6a8ba7cb85dc81919f961b5ca9a9f62d` đã được quan sát ở trạng thái published.

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

2026-08-24 の verification では、PyPI、GitHub Releases、OpenAI Plugins Directory のすべてで Proofline 2.0.2 の published status を確認しました。Git tag は release commit `5328eba3cd907db1190ce2a3be7a5f96ae5b67be` に resolve します。Public PyPI SHA-256 は wheel が `f5e256f8a91a8c61f80e6b588a5bfd102990972d01fe5db6628b378812f45474`、sdist が `59e6f155912a66cffb88493f5e114928c8aa71ef76fe4cab39891bc8feda28bd` です。Submitted plugin ZIP SHA-256 は `c6e8e83ba66e78811dcd6d99011d6454abb367969abf77ca7dbbd1803df8360` で、submission `appsub_6a8ba7cb85dc81919f961b5ca9a9f62d` の published status を観測しました。
