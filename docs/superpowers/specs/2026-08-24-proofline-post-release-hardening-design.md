# Proofline Post-Release Hardening Design

## English

### Status and intent

Proofline 2.0.1 is publicly released on PyPI, GitHub, and the OpenAI Plugins Directory. This hardening program improves public verification, maintenance hygiene, pilot evidence capture, and desktop release readiness without changing the local-first trust boundary or claiming unavailable production evidence.

The approved direction is evidence-first hardening. A minimal issue-only patch would leave the exact-release CI and repository-governance gaps open. Building hosted collaboration now would exceed the shipped single-user architecture and require a separate security design. Therefore this work keeps runtime scope local and makes every new claim independently auditable.

### Deliverable A: exact-ref CI and repository security

CI gains a manual `source_ref` input. A dispatch runs the full existing job set from the default-branch workflow definition while every checkout resolves the explicit immutable ref. This permits a public run against `v2.0.1` without mutating the tag.

CodeQL runs for Python and JavaScript/TypeScript on pull requests, pushes to `main`, a weekly schedule, and manual dispatch. Dependabot covers Python, npm, Cargo, and GitHub Actions weekly. After the change is merged and checks are green, `main` receives branch protection requiring pull requests and the full CI checks, blocking force-push and deletion. Repository homepage metadata points to the public plugin page.

### Deliverable B: public contract maintenance

Issue #6 is obsolete because the documentation rebuild removed `docs/proofline-page.js`; it will be closed with that exact reason rather than replaced by unrelated work.

Issue #7 is completed by documenting a content-free `check-decisions --format json` review-required example in the current trilingual CLI reference and locking the exact public keys and blocking exit code in a real CLI test.

Issue #8 is completed by adding a narrow-screen rule to the self-contained Decision Evidence Package HTML. The decision record collapses to one column, containers use smaller padding, and long identifiers continue to wrap without hiding or truncating provenance. A rendering regression test protects these behaviors and the no-network contract.

### Deliverable C: real-pilot evidence capture

The existing analyzer already rejects synthetic questions and requires a frozen, hashed private dataset. A new freezer validates the five required input files, rejects template or synthetic markers, calculates hashes, and atomically writes `manifest.json`. The trilingual pilot guide defines collection, consent, freeze, analysis, owner-signoff, and publication boundaries.

No real pilot result is created without team-owned inputs. Local tests prove the capture path, not adoption, human usefulness, willingness-to-pay, or production latency. This is an intentional fail-closed boundary.

### Deliverable D: desktop release readiness

A manual desktop workflow builds macOS and Windows packages and emits platform receipts. Experimental builds are explicitly unsigned/unnotarized. Release-grade mode runs a deterministic credential gate before build and fails when required signing/notarization inputs are absent. It never publishes an unsigned artifact as a production release.

The workflow prepares repeatable native packaging; it cannot manufacture Apple Developer ID, Apple notarization credentials, or Windows Authenticode identity. Public signed artifacts remain blocked until those external credentials exist and the resulting packages pass platform verification.

### Testing and release boundary

Behavior changes use red-green TDD. Workflow files are parsed and validated locally, then exercised on GitHub after merge. Full Python, web, egress, build, package-conformance, audit, and E2E gates run before integration. This branch does not overwrite the immutable 2.0.1 release or silently create a new package version.

## Tiếng Việt

### Trạng thái và mục tiêu

Proofline 2.0.1 đã public trên PyPI, GitHub và OpenAI Plugins Directory. Chương trình hardening này bổ sung verification công khai, maintenance hygiene, luồng thu evidence pilot và desktop release readiness mà không thay đổi trust boundary local-first hoặc claim production evidence chưa có.

Hướng đã duyệt là evidence-first hardening. Chỉ sửa issue sẽ bỏ lại gap CI trên exact release và repository governance. Xây hosted collaboration lúc này vượt quá kiến trúc single-user đã phát hành và cần security design riêng. Vì vậy runtime scope vẫn local và mọi claim mới phải audit độc lập được.

### Deliverable A: exact-ref CI và repository security

CI có input thủ công `source_ref`; mọi checkout resolve explicit immutable ref. CodeQL chạy cho Python và JavaScript/TypeScript; Dependabot theo dõi Python, npm, Cargo và GitHub Actions. Sau khi merge và check xanh, `main` bắt buộc PR cùng full CI, cấm force-push và deletion. Homepage repository trỏ tới public plugin page.

### Deliverable B: public contract maintenance

Issue #6 được đóng vì `docs/proofline-page.js` đã bị loại trong documentation rebuild. Issue #7 thêm JSON example content-free vào CLI reference ba ngôn ngữ và khóa exact public keys cùng blocking exit code. Issue #8 thêm narrow-screen CSS cho offline DEP report, giữ mọi provenance field và exact value có thể wrap; regression test bảo vệ no-network contract.

### Deliverable C: thu evidence pilot thật

Freezer mới validate năm input file, từ chối marker template/synthetic, tính hash và ghi `manifest.json` atomically. Pilot guide ba ngôn ngữ mô tả collection, consent, freeze, analysis, owner signoff và publication boundary. Không tạo kết quả pilot thật khi chưa có input do team sở hữu.

### Deliverable D: desktop release readiness

Workflow thủ công build package macOS/Windows và tạo platform receipt. Experimental build được ghi rõ unsigned/unnotarized. Release-grade mode fail trước build nếu thiếu credential signing/notarization và không publish artifact unsigned như production release.

### Testing và release boundary

Mọi behavior change theo red-green TDD. Workflow được parse/validate local rồi chạy thật trên GitHub sau merge. Full Python, web, egress, build, package-conformance, audit và E2E gate chạy trước integration. Branch này không overwrite release 2.0.1 immutable hoặc tự tạo version package mới.

## 日本語

### 状態と目的

Proofline 2.0.1 は PyPI、GitHub、OpenAI Plugins Directory で公開済みです。この hardening は local-first trust boundary を変えず、存在しない production evidence を主張せずに、公開 verification、maintenance、pilot evidence capture、desktop release readiness を改善します。

承認済み方針は evidence-first hardening です。Issue だけの修正では exact-release CI と repository governance の gap が残ります。Hosted collaboration は single-user architecture を超え、別の security design が必要なため対象外です。

### Deliverable A: exact-ref CI と repository security

CI に手動 `source_ref` input を追加し、全 checkout が明示 immutable ref を解決します。CodeQL は Python と JavaScript/TypeScript、Dependabot は Python、npm、Cargo、GitHub Actions を対象にします。Merge と green check 後、`main` は PR と full CI を必須にし、force-push と deletion を禁止します。Repository homepage は public plugin page を指します。

### Deliverable B: public contract maintenance

Issue #6 は documentation rebuild で `docs/proofline-page.js` が削除済みのため close します。Issue #7 は content-free JSON example と exact public key / blocking exit code test を追加します。Issue #8 は offline DEP report に narrow-screen CSS を追加し、全 provenance field と長い値を保持する regression test を追加します。

### Deliverable C: real-pilot evidence capture

新 freezer は五つの input file を検証し、template/synthetic marker を拒否し、hash を計算して `manifest.json` を atomic write します。三言語 pilot guide は collection、consent、freeze、analysis、owner signoff、publication boundary を定義します。Team-owned input なしに real pilot result は作成しません。

### Deliverable D: desktop release readiness

Manual workflow は macOS/Windows package と platform receipt を生成します。Experimental build は unsigned/unnotarized と明記します。Release-grade mode は signing/notarization credential がなければ build 前に fail し、unsigned artifact を production release として publish しません。

### Testing と release boundary

Behavior change は red-green TDD を使います。Workflow は local parse/validation 後、merge 後に GitHub で実行します。Integration 前に Python、web、egress、build、package-conformance、audit、E2E gate を実行します。この branch は immutable 2.0.1 release を上書きせず、新 package version を暗黙作成しません。
