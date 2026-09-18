$ErrorActionPreference = "Stop"
$InstallDir = Join-Path $env:LOCALAPPDATA "SonicStream"
$SaveDir = Join-Path ([Environment]::GetFolderPath("UserProfile")) "Downloads\SonicStream"
$UserKeep = @("data", "profile", ".env")

function Stop-InstalledEngine {
    $python = Join-Path $InstallDir "runtime\python\python.exe"
    if (-not (Test-Path $python)) { return }
    $resolvedPython = (Resolve-Path $python).Path
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ExecutablePath -and ($_.ExecutablePath -eq $resolvedPython)
    } | ForEach-Object {
        Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

if (Test-Path $InstallDir) {
    Stop-InstalledEngine
    $manifestPath = Join-Path $InstallDir "FILES.manifest"
    if (Test-Path $manifestPath) {
        Get-Content $manifestPath | ForEach-Object {
            $rel = $_.Trim()
            if (-not $rel) { return }
            $target = Join-Path $InstallDir $rel
            if (Test-Path $target) { Remove-Item -Force -Recurse $target -ErrorAction SilentlyContinue }
        }
    } else {
        Get-ChildItem -Force $InstallDir | Where-Object { $UserKeep -notcontains $_.Name } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    $leftover = @(Get-ChildItem -Force $InstallDir -ErrorAction SilentlyContinue)
    if (-not $leftover) { Remove-Item -Recurse -Force $InstallDir -ErrorAction SilentlyContinue }
}

$desktop = Join-Path ([Environment]::GetFolderPath("Desktop")) "SonicStream.lnk"
$startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\SonicStream.lnk"
$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup\SonicStream.lnk"
Remove-Item -Force $desktop, $startMenu, $startup -ErrorAction SilentlyContinue

Write-Host "프로그램 파일을 제거했습니다."
Write-Host "받은 영상, .env, data 폴더는 지우지 않았습니다."
if (Test-Path $SaveDir) {
    Write-Host "기본 저장 폴더: $SaveDir"
}
