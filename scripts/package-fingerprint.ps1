# Shared source fingerprint for installer freshness.
# Dot-source from package-windows.ps1 and start-local.ps1.

function Get-SonicStreamSourceFingerprint {
    param([Parameter(Mandatory = $true)][string]$Root)

    $paths = New-Object System.Collections.Generic.List[string]
    foreach ($rel in @(
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
        "scripts\package-windows.ps1",
        "scripts\package-fingerprint.ps1",
        "scripts\start-local.ps1",
        "시작하기.bat",
        "다른PC에설치하기.bat"
    )) {
        $full = Join-Path $Root $rel
        if (Test-Path $full) { $paths.Add($full) }
    }
    $packDir = Join-Path $Root "packaging\windows"
    if (Test-Path $packDir) {
        Get-ChildItem $packDir -File | ForEach-Object { $paths.Add($_.FullName) }
    }
    $appDir = Join-Path $Root "backend\app"
    if (Test-Path $appDir) {
        Get-ChildItem $appDir -Filter "*.py" -File | ForEach-Object { $paths.Add($_.FullName) }
    }
    $srcDir = Join-Path $Root "frontend\src"
    if (Test-Path $srcDir) {
        Get-ChildItem $srcDir -Recurse -File -Include *.ts,*.tsx,*.css,*.json |
            ForEach-Object { $paths.Add($_.FullName) }
    }
    $publicDir = Join-Path $Root "frontend\public"
    if (Test-Path $publicDir) {
        Get-ChildItem $publicDir -Recurse -File | ForEach-Object { $paths.Add($_.FullName) }
    }

    $hasher = [System.Security.Cryptography.SHA256]::Create()
    $concat = New-Object System.Text.StringBuilder
    foreach ($p in ($paths | Sort-Object -Unique)) {
        $hash = (Get-FileHash -LiteralPath $p -Algorithm SHA256).Hash
        [void]$concat.Append($hash)
        [void]$concat.Append("|")
        [void]$concat.Append(($p.Substring($Root.Length)).ToLowerInvariant())
        [void]$concat.Append("`n")
    }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes($concat.ToString())
    $digest = $hasher.ComputeHash($bytes)
    return ([System.BitConverter]::ToString($digest) -replace "-", "").ToLowerInvariant()
}

function Get-SonicStreamGitHead {
    param([Parameter(Mandatory = $true)][string]$Root)
    try {
        $head = & git -C $Root rev-parse HEAD 2>$null
        if ($LASTEXITCODE -eq 0 -and $head) { return "$head".Trim() }
    } catch { }
    return ""
}

function New-SonicStreamBuildManifest {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Fingerprint
    )
    $git = Get-SonicStreamGitHead -Root $Root
    return [ordered]@{
        product           = "SonicStream"
        built_at          = (Get-Date).ToUniversalTime().ToString("o")
        git               = $git
        source_fingerprint = $Fingerprint
        static_ui         = $true
        rule              = "이 설치 ZIP은 빌드 당시 소스와 동일하다. 프론트/백엔드/패키징/카피를 바꾼 뒤에는 다른PC에설치하기.bat으로 다시 만든다."
    }
}

function Get-SonicStreamLastPackagePath {
    param([Parameter(Mandatory = $true)][string]$Root)
    return (Join-Path $Root "dist\last-package.json")
}

function Test-SonicStreamPackageFresh {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$Fingerprint
    )
    $stamp = Get-SonicStreamLastPackagePath -Root $Root
    $zip = Join-Path $Root "dist\SonicStream-Windows.zip"
    if (-not (Test-Path $stamp) -or -not (Test-Path $zip)) {
        return $false
    }
    try {
        $doc = Get-Content -LiteralPath $stamp -Raw -Encoding UTF8 | ConvertFrom-Json
        if ($doc.source_fingerprint -ne $Fingerprint) { return $false }
        return [bool](Test-SonicStreamZip -ZipPath $zip -Fingerprint $Fingerprint)
    } catch {
        return $false
    }
}

function Test-SonicStreamZip {
    param(
        [Parameter(Mandatory = $true)][string]$ZipPath,
        [string]$Fingerprint = ""
    )
    if (-not (Test-Path $ZipPath)) { return $false }
    $item = Get-Item $ZipPath
    if ($item.Length -lt 1024 -or $item.Extension -ne ".zip") { return $false }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $archive = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    try {
        $names = @($archive.Entries | ForEach-Object { $_.FullName.Replace('\', '/') })
        $bats = @($names | Where-Object { $_.ToLowerInvariant().EndsWith(".bat") })
        if ($bats.Count -lt 4) { return $false }
        foreach ($need in @(
            "/BUILD.json",
            "/FILES.json",
            "/backend/app/ai_search.py",
            "/backend/app/transcript.py",
            "/ui/index.html",
            "/runtime/python/python.exe",
            "/runtime/node/node.exe",
            "/runtime/ffmpeg/ffmpeg.exe",
            "/runtime/ffmpeg/ffprobe.exe"
        )) {
            if (-not ($names | Where-Object { $_.EndsWith($need) })) { return $false }
        }
        if ($Fingerprint) {
            $build = $archive.Entries | Where-Object { $_.FullName -eq "SonicStream-Windows/BUILD.json" } | Select-Object -First 1
            if (-not $build) { return $false }
            $reader = New-Object System.IO.StreamReader($build.Open())
            $json = $reader.ReadToEnd()
            $reader.Close()
            $doc = $json | ConvertFrom-Json
            if ($doc.source_fingerprint -ne $Fingerprint) { return $false }
        }
        return $true
    } finally {
        $archive.Dispose()
    }
}
