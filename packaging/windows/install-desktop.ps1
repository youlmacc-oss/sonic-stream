$ErrorActionPreference = "Stop"
$Source = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallDir = Join-Path $env:LOCALAPPDATA "SonicStream"
$UserKeep = @("data", "profile", ".env", "runtime.pid")

if (-not (Test-Path (Join-Path $Source "runtime\python\python.exe"))) {
    Write-Host "설치 구성이 완전하지 않습니다. 압축을 모두 푼 뒤 다시 실행해 주세요."
    exit 1
}
if (-not (Test-Path (Join-Path $Source "ui\index.html"))) {
    Write-Host "화면 파일이 없습니다. 설치 ZIP을 다시 만들어 주세요."
    exit 1
}

function Resolve-SamePath([string]$Left, [string]$Right) {
    try {
        return ((Resolve-Path $Left).Path.TrimEnd('\') -eq (Resolve-Path $Right).Path.TrimEnd('\'))
    } catch {
        return $false
    }
}

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

Write-Host "설치 위치: $InstallDir"
if (Resolve-SamePath $Source $InstallDir) {
    Write-Host "이미 설치 폴더에서 실행 중입니다. 프로그램 파일을 지우지 않습니다."
} else {
    Stop-InstalledEngine
    New-Item -ItemType Directory -Force -Path $InstallDir | Out-Null
    Get-ChildItem -Force $Source | Where-Object { $UserKeep -notcontains $_.Name } | ForEach-Object {
        $dest = Join-Path $InstallDir $_.Name
        if ($_.PSIsContainer) {
            if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
            Copy-Item -Recurse -Force $_.FullName $dest
        } else {
            Copy-Item -Force $_.FullName $dest
        }
    }
}

$manifest = Get-ChildItem -Recurse -File $InstallDir | Where-Object {
    $rel = $_.FullName.Substring($InstallDir.Length).TrimStart('\')
    $top = $rel.Split('\')[0]
    $UserKeep -notcontains $top
} | ForEach-Object { $_.FullName.Substring($InstallDir.Length).TrimStart('\') }
$manifest | Set-Content -Path (Join-Path $InstallDir "FILES.manifest") -Encoding UTF8

function Write-Shortcut($link) {
    $Wsh = New-Object -ComObject WScript.Shell
    $shortcut = $Wsh.CreateShortcut($link)
    $shortcut.TargetPath = Join-Path $InstallDir "실행하기.bat"
    $shortcut.WorkingDirectory = $InstallDir
    $shortcut.WindowStyle = 7
    $shortcut.Description = "SonicStream"
    $shortcut.Save()
}

$startMenuDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
New-Item -ItemType Directory -Force -Path $startMenuDir | Out-Null
Write-Shortcut (Join-Path $startMenuDir "SonicStream.lnk")

Write-Host ""
Write-Host "설치가 끝났습니다."
$desktopAnswer = Read-Host "바탕화면에 바로가기를 만들까요? [Y/n]"
if ($desktopAnswer -notmatch '^[nN]') {
    Write-Shortcut (Join-Path ([Environment]::GetFolderPath("Desktop")) "SonicStream.lnk")
    Write-Host "바탕화면 바로가기를 만들었습니다."
} else {
    Write-Host "바탕화면 바로가기는 만들지 않았습니다. 시작 메뉴의 SonicStream으로 실행할 수 있습니다."
}

$key = Read-Host "OpenAI API 키를 넣을까요? 없으면 Enter"
$key = ($key | ForEach-Object { $_.Trim() })
if ($key) {
    $envFile = Join-Path $InstallDir ".env"
    $lines = @()
    if (Test-Path $envFile) {
        $lines = Get-Content -Path $envFile -Encoding UTF8
    }
    $replaced = $false
    $next = foreach ($line in $lines) {
        if ($line -match '^\s*OPENAI_API_KEY=') {
            $replaced = $true
            "OPENAI_API_KEY=$key"
        } else {
            $line
        }
    }
    if (-not $replaced) { $next += "OPENAI_API_KEY=$key" }
    if (-not ($next | Where-Object { $_ -match '^\s*OPENAI_MODEL=' })) { $next += "OPENAI_MODEL=gpt-4o-mini" }
    Set-Content -Path $envFile -Value $next -Encoding UTF8
    Write-Host "API 키를 이 컴퓨터에 저장했습니다."
}

Write-Host "받은 영상은 다운로드\SonicStream 폴더에 남습니다."
Write-Host "프로그램을 지워도 받은 파일과 .env, data 폴더는 삭제하지 않습니다."
Write-Host "프로그램을 시작합니다."
Start-Process (Join-Path $InstallDir "실행하기.bat")
