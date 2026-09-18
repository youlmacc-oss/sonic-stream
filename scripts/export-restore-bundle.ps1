$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Work = Join-Path $env:TEMP "sonicstream-restore-export"
$Stage = Join-Path $Work "tree"
if (Test-Path $Work) { Remove-Item -Recurse -Force $Work }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

$include = @(
    "backend\main.py",
    "backend\error_logger.py",
    "backend\models.py",
    "backend\requirements.txt",
    "backend\.env.example",
    "frontend\package.json",
    "frontend\package-lock.json",
    "frontend\next.config.ts",
    "frontend\tsconfig.json",
    "frontend\postcss.config.mjs",
    "frontend\next-env.d.ts",
    "frontend\eslint.config.mjs",
    "frontend\.env.example",
    "scripts\start-local.ps1",
    "scripts\package-windows.ps1",
    "scripts\package-fingerprint.ps1",
    "scripts\export-restore-bundle.ps1",
    "scripts\restore-from-md.ps1"
)
foreach ($rel in $include) {
    $src = Join-Path $Root $rel
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $dest = Join-Path $Stage $rel
    New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
    Copy-Item -LiteralPath $src -Destination $dest -Force
}
Get-ChildItem -LiteralPath $Root -File -Filter *.bat | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination (Join-Path $Stage $_.Name) -Force
}

Copy-Item -Recurse -Force (Join-Path $Root "backend\app") (Join-Path $Stage "backend\app")
Copy-Item -Recurse -Force (Join-Path $Root "backend\tests") (Join-Path $Stage "backend\tests")
Copy-Item -Recurse -Force (Join-Path $Root "frontend\src") (Join-Path $Stage "frontend\src")
if (Test-Path (Join-Path $Root "frontend\public")) {
    Copy-Item -Recurse -Force (Join-Path $Root "frontend\public") (Join-Path $Stage "frontend\public")
}
Copy-Item -Recurse -Force (Join-Path $Root "packaging\windows") (Join-Path $Stage "packaging\windows")

Get-ChildItem $Stage -Recurse -Include *.pyc,__pycache__ | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue

$files = Get-ChildItem $Stage -Recurse -File | Sort-Object FullName
$manifest = foreach ($file in $files) {
    [ordered]@{
        path   = ($file.FullName.Substring($Stage.Length)).TrimStart('\').Replace('\', '/')
        bytes  = $file.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    }
}
$manifestPath = Join-Path $Work "manifest.json"
($manifest | ConvertTo-Json -Depth 4) | Set-Content $manifestPath -Encoding UTF8

$tar = Join-Path $Work "source.tar"
if (Test-Path $tar) { Remove-Item $tar }
Push-Location $Stage
tar -cf $tar *
Pop-Location
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($tar))
$sha = (Get-FileHash -Algorithm SHA256 -Path $tar).Hash.ToLowerInvariant()

$ops = Join-Path $Root "YOUTUBE_OPS.md"
$text = Get-Content -LiteralPath $ops -Raw -Encoding UTF8
$marker = "<!-- SONICSTREAM_RESTORE_BEGIN -->"
$end = "<!-- SONICSTREAM_RESTORE_END -->"
$startIdx = $text.LastIndexOf($marker)
if ($startIdx -ge 0) {
    $endIdx = $text.LastIndexOf($end)
    if ($endIdx -lt 0 -or $endIdx -le $startIdx) { throw "restore end marker missing" }
    $text = $text.Substring(0, $startIdx).TrimEnd() + "`r`n`r`n"
}

$block = @"
$marker
## Restore appendix (machine readable)

Source tarball for a folder that already has the four MD files. No git clone required.

1. Put PRD.md, ARCHITECTURE.md, UI_SPEC.md, YOUTUBE_OPS.md in an empty folder.
2. Run the PowerShell below in that folder.

``````powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\restore-from-md.ps1
``````

If restore-from-md.ps1 is missing, run:

``````powershell
`$md = Get-Content -Raw .\YOUTUBE_OPS.md
`$startToken = '<!-- SONICSTREAM_RESTORE_TAR_B64 -->'
`$endToken = '<!-- SONICSTREAM_RESTORE_TAR_END -->'
`$start = `$md.LastIndexOf(`$startToken)
`$end = `$md.LastIndexOf(`$endToken)
`$b64 = (`$md.Substring(`$start + `$startToken.Length, `$end - `$start - `$startToken.Length) -replace '[^A-Za-z0-9+/=]','').Trim()
[IO.File]::WriteAllBytes((Join-Path `$pwd 'source.tar'), [Convert]::FromBase64String(`$b64))
tar -xf source.tar
``````

TAR SHA-256: $sha
File count: $($manifest.Count)

<!-- SONICSTREAM_RESTORE_MANIFEST -->
$(($manifest | ConvertTo-Json -Compress -Depth 4))
<!-- SONICSTREAM_RESTORE_TAR_B64 -->
$b64
<!-- SONICSTREAM_RESTORE_TAR_END -->
$end
"@

$out = $text.TrimEnd() + "`r`n`r`n" + $block
$utf8 = New-Object System.Text.UTF8Encoding $true
[System.IO.File]::WriteAllText($ops, $out, $utf8)
Write-Host "RESTORE_APPENDIX files=$($manifest.Count) sha=$sha"
