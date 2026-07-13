#!/usr/bin/env bash
set -euo pipefail

tag="${1:-}"
if [[ -z "$tag" ]]; then
  echo "usage: scripts/release_local.sh vMAJOR.MINOR.PATCH" >&2
  exit 2
fi

root=$(git rev-parse --show-toplevel)
cd "$root"

if [[ $(git branch --show-current) != "main" ]]; then
  echo "local release requires the main branch" >&2
  exit 2
fi
if [[ -n $(git status --porcelain) ]]; then
  echo "local release requires a clean working tree" >&2
  exit 2
fi

git fetch origin main --tags
if [[ $(git rev-parse HEAD) != $(git rev-parse origin/main) ]]; then
  echo "main must exactly match origin/main" >&2
  exit 2
fi
if ! .venv/bin/python scripts/check_ci_skip.py; then
  echo "local releases require the main push to skip quota-limited GitHub Actions" >&2
  exit 2
fi
if git rev-parse -q --verify "refs/tags/$tag" >/dev/null; then
  echo "tag already exists locally: $tag" >&2
  exit 2
fi
if git ls-remote --exit-code --tags origin "refs/tags/$tag" >/dev/null 2>&1; then
  echo "tag already exists on origin: $tag" >&2
  exit 2
fi
if gh release view "$tag" >/dev/null 2>&1; then
  echo "GitHub release already exists: $tag" >&2
  exit 2
fi

.venv/bin/python scripts/release_check.py --tag "$tag"
make test
make check

release_dir=$(mktemp -d "${TMPDIR:-/tmp}/proofline-release.XXXXXX")
smoke_dir=$(mktemp -d "${TMPDIR:-/tmp}/proofline-smoke.XXXXXX")
cleanup() {
  rm -rf "$release_dir" "$smoke_dir"
}
trap cleanup EXIT

.venv/bin/python -m build --outdir "$release_dir"
npm run build:web
tar -czf "$release_dir/proofline-web-$tag.tar.gz" -C apps/web/dist .

python3 -m venv "$smoke_dir/venv"
"$smoke_dir/venv/bin/pip" install --quiet "$release_dir"/*.whl
installed_version=$("$smoke_dir/venv/bin/proofline" --version)
installed_version=${installed_version#proofline }
platform_slug=$(uname -s | tr '[:upper:]' '[:lower:]')-$(uname -m)
.venv/bin/python scripts/platform_release_receipt.py \
  --proofline "$smoke_dir/venv/bin/proofline" \
  --python "$smoke_dir/venv/bin/python" \
  --artifact "$release_dir/proofline-$installed_version-py3-none-any.whl" \
  --expected-version "$installed_version" \
  --qualify-os-keyring \
  --output "$release_dir/proofline-platform-$tag-$platform_slug.json" >/dev/null
(
  cd "$release_dir"
  shasum -a 256 proofline-* > SHA256SUMS
)

git tag -a "$tag" -m "Proofline $tag"
if ! git push origin "$tag"; then
  git tag -d "$tag" >/dev/null
  echo "tag push failed; removed the local tag" >&2
  exit 1
fi

release_args=(
  "$tag"
  "$release_dir"/proofline-*
  "$release_dir/SHA256SUMS"
  --verify-tag
  --title "Proofline $tag"
  --notes-file "docs/releases/$tag.md"
)
if [[ "$tag" == v0.* || "$tag" == *-* ]]; then
  release_args+=(--prerelease)
fi
gh release create "${release_args[@]}"
