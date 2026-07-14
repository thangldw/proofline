param(
  [Parameter(Mandatory = $true)]
  [string]$Tag
)

$ErrorActionPreference = "Stop"
$Root = (git rev-parse --show-toplevel).Trim()
Set-Location $Root

if ((git branch --show-current).Trim() -ne "main") { throw "Windows release requires main" }
if (git status --porcelain) { throw "Windows release requires a clean working tree" }
git fetch origin main --tags
if ((git rev-parse HEAD).Trim() -ne (git rev-parse origin/main).Trim()) {
  throw "main must exactly match origin/main"
}

$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Pip = Join-Path $Root ".venv\Scripts\pip.exe"
$Proofline = Join-Path $Root ".venv\Scripts\proofline.exe"
if (-not (Test-Path $Python)) { throw "Run py -3.12 -m venv .venv first" }

& $Python scripts/check_ci_skip.py
& $Python scripts/release_check.py --tag $Tag
& $Python -m pytest -q
npm run test:web
& $Python -m ruff check .
& $Python -m ruff format --check .
npm run build:web
& $Python scripts/sync_web_bundle.py --check
& $Proofline eval-extraction --dataset evals/extraction/seed-v1.json --min-precision 1 --min-recall 1 --min-f1 1 --min-evidence-resolution 1 --min-expected-evidence-accuracy 1 --min-negative-source-accuracy 1
& $Proofline eval --dataset evals/retrieval/seed-v2.json --min-recall 1 --min-ndcg 1 --min-expected-empty-accuracy 1
& $Proofline eval-grounded --dataset evals/grounded-qa/seed-v1.json --min-citation-resolution 1 --min-citation-precision 1 --min-grounded-success 1 --min-status-accuracy 1

$ReleaseDir = Join-Path ([System.IO.Path]::GetTempPath()) ("proofline-windows-" + [guid]::NewGuid())
$SmokeDir = Join-Path ([System.IO.Path]::GetTempPath()) ("proofline-smoke-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $ReleaseDir, $SmokeDir | Out-Null
try {
  & $Python -m build --outdir $ReleaseDir
  npm run build:web
  Compress-Archive -Path "apps\web\dist\*" -DestinationPath (Join-Path $ReleaseDir "proofline-web-$Tag.zip")

  & $Python scripts/build_desktop_sidecar.py --target x86_64-pc-windows-msvc
  npm run build --workspace "@proofline/desktop"
  $Msi = Get-ChildItem "apps\desktop\src-tauri\target\release\bundle\msi\*.msi" | Select-Object -First 1
  $Nsis = Get-ChildItem "apps\desktop\src-tauri\target\release\bundle\nsis\*.exe" | Select-Object -First 1
  if (-not $Msi -or -not $Nsis) { throw "Tauri did not produce both MSI and NSIS installers" }
  $MsiAsset = Join-Path $ReleaseDir "proofline-desktop-$Tag-windows-x64.msi"
  $NsisAsset = Join-Path $ReleaseDir "proofline-desktop-$Tag-windows-x64-setup.exe"
  Copy-Item $Msi.FullName $MsiAsset
  Copy-Item $Nsis.FullName $NsisAsset
  $Sidecar = "apps\desktop\src-tauri\binaries\proofline-sidecar-x86_64-pc-windows-msvc.exe"
  & $Python scripts/windows_desktop_receipt.py --sidecar $Sidecar --installer $MsiAsset --installer $NsisAsset --expected-version $Tag.TrimStart("v") --output (Join-Path $ReleaseDir "proofline-desktop-$Tag-windows-x64.json")

  py -3.12 -m venv (Join-Path $SmokeDir "venv")
  $SmokePython = Join-Path $SmokeDir "venv\Scripts\python.exe"
  $SmokeProofline = Join-Path $SmokeDir "venv\Scripts\proofline.exe"
  $Wheel = Get-ChildItem "$ReleaseDir\*.whl" | Select-Object -First 1
  & $SmokePython -m pip install --quiet $Wheel.FullName
  & $Python scripts/platform_release_receipt.py --proofline $SmokeProofline --python $SmokePython --artifact $Wheel.FullName --expected-version $Tag.TrimStart("v") --qualify-os-keyring --output (Join-Path $ReleaseDir "proofline-platform-$Tag-windows-x64.json")

  $ChecksumPath = Join-Path $ReleaseDir "SHA256SUMS"
  Get-ChildItem "$ReleaseDir\proofline-*" | ForEach-Object {
    $Hash = (Get-FileHash -Algorithm SHA256 $_.FullName).Hash.ToLowerInvariant()
    "$Hash  $($_.Name)"
  } | Set-Content -Encoding ascii $ChecksumPath

  git tag -a $Tag -m "Proofline $Tag"
  git push origin $Tag
  $Assets = @(Get-ChildItem "$ReleaseDir\proofline-*").FullName + $ChecksumPath
  gh release create $Tag $Assets --verify-tag --title "Proofline $Tag" --notes-file "docs/releases/$Tag.md" --prerelease
}
finally {
  Remove-Item -Recurse -Force $ReleaseDir, $SmokeDir -ErrorAction SilentlyContinue
}
