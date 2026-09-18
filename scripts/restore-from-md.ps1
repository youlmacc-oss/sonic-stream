param(
    [switch]$VerifyOnly
)

$ErrorActionPreference = "Stop"
$Here = Get-Location
$Ops = Join-Path $Here "YOUTUBE_OPS.md"
if (-not (Test-Path $Ops)) { $Ops = Join-Path $PSScriptRoot "..\YOUTUBE_OPS.md" }
if (-not (Test-Path $Ops)) { throw "YOUTUBE_OPS.md 가 없습니다." }

function Test-SafeRestorePath([string]$Rel) {
    $norm = ($Rel -replace '\\', '/').Trim()
    if (-not $norm) { return $false }
    if ($norm.StartsWith('/') -or $norm.StartsWith('\')) { return $false }
    if ($norm -match '^[A-Za-z]:') { return $false }
    $parts = $norm.Split('/', [System.StringSplitOptions]::RemoveEmptyEntries)
    foreach ($part in $parts) {
        if ($part -eq '..') { return $false }
    }
    return $true
}

function Read-AppendixManifest([string]$Appendix, [string]$ManToken, [string]$StartToken) {
    $manStart = $Appendix.LastIndexOf($ManToken)
    $manEnd = $Appendix.LastIndexOf($StartToken)
    if ($manStart -lt 0 -or $manEnd -le $manStart) {
        throw "복원 매니페스트 표식이 없습니다."
    }
    $json = $Appendix.Substring($manStart + $ManToken.Length, $manEnd - $manStart - $ManToken.Length).Trim()
    if (-not $json) { throw "복원 매니페스트가 비어 있습니다." }
    try {
        $parsed = $json | ConvertFrom-Json
    } catch {
        throw "복원 매니페스트를 읽지 못했습니다."
    }
    if ($null -eq $parsed) { throw "복원 매니페스트를 읽지 못했습니다." }
    $items = @($parsed)
    if ($items.Count -eq 0) { throw "복원 매니페스트가 비어 있습니다." }
    foreach ($item in $items) {
        if (-not $item.path -or -not $item.sha256) { throw "복원 매니페스트 항목이 올바르지 않습니다." }
        if (-not (Test-SafeRestorePath ([string]$item.path))) {
            throw "허용하지 않은 매니페스트 경로: $($item.path)"
        }
    }
    return $items
}

function Assert-RestoredFiles($Items, [string]$Root) {
    $failed = 0
    $seen = New-Object 'System.Collections.Generic.HashSet[string]'
    foreach ($item in $Items) {
        $rel = ([string]$item.path) -replace '/', '\'
        if (-not $seen.Add($rel.ToLowerInvariant())) {
            Write-Host "중복: $($item.path)"
            $failed++
            continue
        }
        $path = Join-Path $Root $rel
        if (-not (Test-Path -LiteralPath $path)) {
            Write-Host "누락: $($item.path)"
            $failed++
            continue
        }
        $itemInfo = Get-Item -LiteralPath $path -Force
        if ($itemInfo.Attributes -band [IO.FileAttributes]::ReparsePoint) {
            Write-Host "링크 거부: $($item.path)"
            $failed++
            continue
        }
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash.ToLowerInvariant()
        if ($hash -ne $item.sha256) {
            Write-Host "해시 불일치: $($item.path)"
            $failed++
        }
    }
    $allowedExtra = @('PRD.md', 'ARCHITECTURE.md', 'UI_SPEC.md', 'YOUTUBE_OPS.md', 'source.tar')
    $extras = Get-ChildItem -LiteralPath $Root -Recurse -File -Force | Where-Object {
        $rel = $_.FullName.Substring($Root.Length).TrimStart('\').Replace('\', '/')
        -not $seen.Contains($rel.Replace('/', '\').ToLowerInvariant()) -and ($allowedExtra -notcontains $_.Name)
    }
    foreach ($extra in $extras) {
        Write-Host "여분 파일: $($extra.FullName.Substring($Root.Length).TrimStart('\'))"
        $failed++
    }
    if ($failed -gt 0) { throw "복원 검증 실패: $failed" }
    Write-Host "복원 검증 통과: $($Items.Count) files"
}

$md = Get-Content -LiteralPath $Ops -Raw -Encoding UTF8
$beginToken = "<!-- SONICSTREAM_RESTORE_BEGIN -->"
$endAppendixToken = "<!-- SONICSTREAM_RESTORE_END -->"
$manToken = "<!-- SONICSTREAM_RESTORE_MANIFEST -->"
$startToken = "<!-- SONICSTREAM_RESTORE_TAR_B64 -->"
$endToken = "<!-- SONICSTREAM_RESTORE_TAR_END -->"

$begin = $md.LastIndexOf($beginToken)
$appendixEnd = $md.LastIndexOf($endAppendixToken)
if ($begin -lt 0 -or $appendixEnd -le $begin) {
    throw "복원 부록 영역이 없습니다."
}
$appendix = $md.Substring($begin, $appendixEnd - $begin)

$start = $appendix.LastIndexOf($startToken)
$end = $appendix.LastIndexOf($endToken)
if ($start -lt 0 -or $end -le $start) { throw "복원 TAR 부록이 없습니다." }

$items = Read-AppendixManifest $appendix $manToken $startToken

if (-not $VerifyOnly) {
    $shaMatch = [regex]::Match($appendix, 'TAR SHA-256:\s*([0-9a-fA-F]{64})')
    if (-not $shaMatch.Success) { throw "부록 TAR 해시가 없습니다." }
    $expectedSha = $shaMatch.Groups[1].Value.ToLowerInvariant()

    $b64 = $appendix.Substring($start + $startToken.Length, $end - $start - $startToken.Length)
    $b64 = ($b64 -replace "[^A-Za-z0-9+/=]", "").Trim()
    if (-not $b64) { throw "복원 TAR 데이터가 비어 있습니다." }
    $tar = Join-Path $Here "source.tar"
    [IO.File]::WriteAllBytes($tar, [Convert]::FromBase64String($b64))
    $actualSha = (Get-FileHash -Algorithm SHA256 -LiteralPath $tar).Hash.ToLowerInvariant()
    if ($actualSha -ne $expectedSha) {
        throw "TAR 해시가 부록과 다릅니다."
    }

    $listed = & tar -tf $tar
    if ($LASTEXITCODE -ne 0) { throw "TAR 목록을 읽지 못했습니다." }
    $entryCount = 0
    foreach ($entry in $listed) {
        $name = ([string]$entry).Trim().TrimEnd('/').Replace('\', '/')
        if (-not $name) { continue }
        if (-not (Test-SafeRestorePath $name)) { throw "허용하지 않은 TAR 경로: $name" }
        $entryCount++
    }
    if ($entryCount -le 0) { throw "TAR 엔트리가 없습니다." }

    $tv = & tar -tvf $tar
    if ($LASTEXITCODE -ne 0) { throw "TAR 상세 목록을 읽지 못했습니다." }
    foreach ($line in $tv) {
        $text = [string]$line
        if ($text -match '^[lL]' -or $text -match '\s->\s') {
            throw "허용하지 않은 TAR 링크: $text"
        }
    }

    tar -xf $tar
    if ($LASTEXITCODE -ne 0) { throw "tar 풀기에 실패했습니다." }
}

Assert-RestoredFiles $items $Here.Path
if (-not $VerifyOnly) {
    Write-Host "이어서 backend venv와 frontend npm ci 후 시작하기.bat을 실행하세요. 실키는 넣지 않은 상태입니다."
}
