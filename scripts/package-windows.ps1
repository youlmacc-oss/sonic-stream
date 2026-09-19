# 기본설계: 이 스크립트는 현재 워크트리로 설치 ZIP을 매번 다시 만든다.
# 프론트/백엔드/패키징을 바꾼 뒤 다른 PC에 주려면 반드시 다시 실행한다.
# 진입점: 다른PC에설치하기.bat
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "package-fingerprint.ps1")
$SourceFingerprint = Get-SonicStreamSourceFingerprint -Root $Root
$Cache = Join-Path $Root "packaging\cache"
$Stage = Join-Path $Root "dist\SonicStream-Windows"
$ZipPath = Join-Path $Root "dist\SonicStream-Windows.zip"
$PythonUrl = "https://www.python.org/ftp/python/3.11.9/python-3.11.9-embed-amd64.zip"
$PythonZip = Join-Path $Cache "python-3.11.9-embed-amd64.zip"
$GetPipUrl = "https://bootstrap.pypa.io/get-pip.py"
$GetPip = Join-Path $Cache "get-pip.py"
$NodeVersion = "22.19.0"
$NodeUrl = "https://nodejs.org/dist/v$NodeVersion/node-v$NodeVersion-win-x64.zip"
$NodeZip = Join-Path $Cache "node-v$NodeVersion-win-x64.zip"
$FfmpegUrl = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
$FfmpegZip = Join-Path $Cache "ffmpeg-release-essentials.zip"

function Get-OfficialFile([string]$Url, [string]$Dest, [string]$Sha256 = "") {
    if (-not (Test-Path $Dest)) {
        New-Item -ItemType Directory -Force -Path (Split-Path $Dest) | Out-Null
        Write-Host "내려받는 중: $Url"
        Invoke-WebRequest -Uri $Url -OutFile $Dest -UseBasicParsing
    } else {
        Write-Host "캐시 사용: $Dest"
    }
    if ($Sha256) {
        $actual = (Get-FileHash -Algorithm SHA256 -Path $Dest).Hash.ToLowerInvariant()
        if ($actual -ne $Sha256.ToLowerInvariant()) {
            throw "해시가 일치하지 않습니다: $Dest"
        }
        Write-Host "해시 확인: $Dest"
    }
}

function Assert-FileHasSignature([string]$Path) {
    if (-not (Test-Path $Path)) { return }
    $sig = Get-AuthenticodeSignature -FilePath $Path
    if ($sig.Status -eq "Valid") {
        Write-Host "서명 확인: $($sig.SignerCertificate.Subject) ($Path)"
        return
    }
    Write-Host "서명 없음 또는 미확인: $Path ($($sig.Status))"
}

New-Item -ItemType Directory -Force -Path $Cache, (Split-Path $Stage) | Out-Null
if (Test-Path $Stage) { Remove-Item -Recurse -Force $Stage }
New-Item -ItemType Directory -Force -Path $Stage | Out-Null

function Assert-LastExit([string]$Label) {
    if ($LASTEXITCODE -ne 0) { throw "$Label 실패 (exit $LASTEXITCODE)" }
}

Write-Host "화면을 설치용으로 만듭니다..."
$Frontend = Join-Path $Root "frontend"
$OutDir = Join-Path $Frontend "out"
if (Test-Path $OutDir) { Remove-Item -Recurse -Force $OutDir }
$env:SONICSTREAM_STATIC = "1"
Remove-Item Env:NEXT_PUBLIC_API_URL -ErrorAction SilentlyContinue
$lock = Join-Path $Frontend "package-lock.json"
if (-not (Test-Path $lock)) {
    throw "frontend/package-lock.json 이 없습니다. 잠금파일로 npm ci 해야 빌드할 수 있습니다."
}
Push-Location $Frontend
npm ci
if ($LASTEXITCODE -ne 0) {
    throw "npm ci 실패 (exit $LASTEXITCODE). 기존 node_modules로 이어가지 않습니다. 원인을 고치거나 깨끗한 폴더에서 다시 실행하세요."
}
npm run build
Assert-LastExit "npm run build"
Pop-Location
if (-not (Test-Path (Join-Path $OutDir "index.html"))) {
    throw "정적 화면 빌드에 실패했습니다."
}

Get-OfficialFile $PythonUrl $PythonZip
Get-OfficialFile $GetPipUrl $GetPip
Get-OfficialFile $NodeUrl $NodeZip "ea3fad0e67a991d8477d8c01344b56e69c676ccb733f065b22436994b1253f86"
Get-OfficialFile $FfmpegUrl $FfmpegZip

$Runtime = Join-Path $Stage "runtime"
$PythonDir = Join-Path $Runtime "python"
$NodeDir = Join-Path $Runtime "node"
$FfmpegDir = Join-Path $Runtime "ffmpeg"
New-Item -ItemType Directory -Force -Path $PythonDir, $NodeDir, $FfmpegDir | Out-Null

Expand-Archive -Path $PythonZip -DestinationPath $PythonDir -Force
$Pth = Get-ChildItem $PythonDir -Filter "python*._pth" | Select-Object -First 1
if (-not $Pth) { throw "embeddable Python _pth 파일을 찾지 못했습니다." }
@"
python311.zip
.
Lib\site-packages
..\..\backend
import site
"@ | Set-Content -Path $Pth.FullName -Encoding ascii

$PythonExe = Join-Path $PythonDir "python.exe"
& $PythonExe $GetPip
if ($LASTEXITCODE -ne 0) { throw "get-pip 설치에 실패했습니다." }
& $PythonExe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw "pip 업그레이드에 실패했습니다." }
& $PythonExe -m pip install -r (Join-Path $Root "backend\requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "백엔드 패키지 설치에 실패했습니다." }
& $PythonExe -c "import fastapi, uvicorn, yt_dlp, sse_starlette, openai; print('PY_OK', yt_dlp.version.__version__)"
if ($LASTEXITCODE -ne 0) { throw "내장 Python 패키지 확인에 실패했습니다." }

$NodeUnpack = Join-Path $Cache "node-unpack"
if (Test-Path $NodeUnpack) { Remove-Item -Recurse -Force $NodeUnpack }
Expand-Archive -Path $NodeZip -DestinationPath $NodeUnpack -Force
$NodeSource = Get-ChildItem $NodeUnpack -Directory | Select-Object -First 1
Copy-Item -Force (Join-Path $NodeSource.FullName "node.exe") (Join-Path $NodeDir "node.exe")

$FfmpegUnpack = Join-Path $Cache "ffmpeg-unpack"
if (Test-Path $FfmpegUnpack) { Remove-Item -Recurse -Force $FfmpegUnpack }
Expand-Archive -Path $FfmpegZip -DestinationPath $FfmpegUnpack -Force
$FfmpegBin = Get-ChildItem $FfmpegUnpack -Recurse -Filter "ffmpeg.exe" | Select-Object -First 1
if (-not $FfmpegBin) { throw "FFmpeg 실행 파일을 찾지 못했습니다." }
Copy-Item -Force $FfmpegBin.FullName (Join-Path $FfmpegDir "ffmpeg.exe")
$Ffprobe = Join-Path $FfmpegBin.DirectoryName "ffprobe.exe"
if (Test-Path $Ffprobe) { Copy-Item -Force $Ffprobe (Join-Path $FfmpegDir "ffprobe.exe") }

Assert-FileHasSignature (Join-Path $PythonDir "python.exe")
Assert-FileHasSignature (Join-Path $NodeDir "node.exe")
Assert-FileHasSignature (Join-Path $FfmpegDir "ffmpeg.exe")

$BackendDest = Join-Path $Stage "backend"
New-Item -ItemType Directory -Force -Path (Join-Path $BackendDest "app") | Out-Null
Copy-Item -Force (Join-Path $Root "backend\main.py") $BackendDest
Copy-Item -Force (Join-Path $Root "backend\error_logger.py") $BackendDest
Copy-Item -Force (Join-Path $Root "backend\requirements.txt") $BackendDest
if (Test-Path (Join-Path $Root "backend\models.py")) {
    Copy-Item -Force (Join-Path $Root "backend\models.py") $BackendDest
}
if (Test-Path (Join-Path $Root "backend\.env.example")) {
    Copy-Item -Force (Join-Path $Root "backend\.env.example") $BackendDest
}
Copy-Item -Force (Join-Path $Root "backend\app\*.py") (Join-Path $BackendDest "app")
if (Test-Path (Join-Path $BackendDest "logs")) {
    Remove-Item -Recurse -Force (Join-Path $BackendDest "logs")
}
& $PythonExe -c "import main; print('MAIN_OK')"
if ($LASTEXITCODE -ne 0) { throw "내장 Python이 backend를 찾지 못합니다." }

Copy-Item -Recurse -Force $OutDir (Join-Path $Stage "ui")
$PackDir = Join-Path $Root "packaging\windows"
$packFiles = @(Get-ChildItem -LiteralPath $PackDir -File)
if ($packFiles.Count -lt 8) { throw "packaging/windows 파일이 부족합니다." }
foreach ($file in $packFiles) {
    Copy-Item -LiteralPath $file.FullName -Destination (Join-Path $Stage $file.Name) -Force
}
$stageBats = @(Get-ChildItem -LiteralPath $Stage -File -Filter "*.bat")
if ($stageBats.Count -lt 4) { throw "설치/실행 bat이 스테이지에 없습니다." }

$SourceFingerprint = Get-SonicStreamSourceFingerprint -Root $Root
$BuildManifest = New-SonicStreamBuildManifest -Root $Root -Fingerprint $SourceFingerprint
$stageFiles = Get-ChildItem -LiteralPath $Stage -Recurse -File | Sort-Object FullName
$fileManifest = foreach ($file in $stageFiles) {
    [ordered]@{
        path   = ($file.FullName.Substring($Stage.Length)).TrimStart('\').Replace('\', '/')
        bytes  = $file.Length
        sha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath $file.FullName).Hash.ToLowerInvariant()
    }
}
$BuildManifest["file_count"] = @($fileManifest).Count
$BuildManifest["python"] = "3.11.9"
$BuildManifest["node"] = $NodeVersion
$BuildJson = Join-Path $Stage "BUILD.json"
$BuildManifest | ConvertTo-Json | Set-Content -Path $BuildJson -Encoding UTF8
$FilesJson = Join-Path $Stage "FILES.json"
[ordered]@{
    source_fingerprint = $SourceFingerprint
    file_count         = @($fileManifest).Count
    files              = @($fileManifest)
} | ConvertTo-Json -Depth 4 | Set-Content -Path $FilesJson -Encoding UTF8

$ZipTmp = Join-Path $Root "dist\SonicStream-Windows.next.zip"
if (Test-Path $ZipTmp) { Remove-Item -Force $ZipTmp }
Write-Host "압축 파일을 생성합니다..."
Compress-Archive -Path $Stage -DestinationPath $ZipTmp -Force -CompressionLevel Optimal
if (-not (Test-SonicStreamZip -ZipPath $ZipTmp -Fingerprint $SourceFingerprint)) {
    if (Test-Path $ZipTmp) { Remove-Item -Force $ZipTmp }
    throw "만든 ZIP이 필수 파일/지문 검사를 통과하지 못했습니다. 이전 ZIP은 그대로 둡니다."
}
if (Test-Path $ZipPath) {
    $ZipBackup = Join-Path $Root "dist\SonicStream-Windows.previous.zip"
    try {
        [System.IO.File]::Replace($ZipTmp, $ZipPath, $ZipBackup)
    } catch {
        if (Test-Path $ZipTmp) { Remove-Item -Force $ZipTmp -ErrorAction SilentlyContinue }
        throw "최종 ZIP 교체에 실패했습니다. 이전 파일을 유지합니다: $ZipPath"
    }
    Remove-Item -Force $ZipBackup -ErrorAction SilentlyContinue
} else {
    Move-Item -Force $ZipTmp $ZipPath
}

$HandOffDir = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads\SonicStream"
New-Item -ItemType Directory -Force -Path $HandOffDir | Out-Null
$HandOffZip = Join-Path $HandOffDir "SonicStream-Windows.zip"
Copy-Item -Force $ZipPath $HandOffZip

$Uploaded = $false
if ($env:SONICSTREAM_UPLOAD_RELEASE -eq "1" -and (Get-Command gh -ErrorAction SilentlyContinue)) {
    $existing = gh release view windows --json tagName 2>$null
    if ($LASTEXITCODE -ne 0) {
        gh release create windows $ZipPath --title "SonicStream Windows 설치 파일" --notes "사이트에서 동의하고 설치하기를 누르면 이 파일을 받아 자동 설치합니다."
        Assert-LastExit "gh release create"
    } else {
        gh release upload windows $ZipPath --clobber
        Assert-LastExit "gh release upload"
    }
    $Uploaded = $true
}

$LastPackage = Get-SonicStreamLastPackagePath -Root $Root
$stamp = [ordered]@{}
foreach ($key in $BuildManifest.Keys) { $stamp[$key] = $BuildManifest[$key] }
$stamp["zip_sha256"] = (Get-FileHash -Algorithm SHA256 -Path $ZipPath).Hash.ToLowerInvariant()
$stamp["release_uploaded"] = $Uploaded
$stamp | ConvertTo-Json | Set-Content -Path $LastPackage -Encoding UTF8

Write-Host ""
Write-Host "설치 파일을 현재 소스와 같게 만들었습니다."
Write-Host "  $ZipPath"
Write-Host "  지문: $SourceFingerprint"
Write-Host "다른 PC로 복사하려면 아래 파일도 사용할 수 있습니다."
Write-Host "  $HandOffZip"
Write-Host "소스를 다시 바꾸면 이 스크립트(다른PC에설치하기.bat)를 또 실행하세요."
