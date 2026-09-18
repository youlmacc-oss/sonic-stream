$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $Root "runtime\python\python.exe"
$NodeDir = Join-Path $Root "runtime\node"
$FfmpegDir = Join-Path $Root "runtime\ffmpeg"
$Backend = Join-Path $Root "backend"
$UiDir = Join-Path $Root "ui"
$PidFile = Join-Path $Root "runtime.pid"
$ProfileDir = Join-Path $Root "profile"
$Port = 8011

if (-not (Test-Path $Python)) {
    Write-Host "실행 파일이 없습니다. 설치하기.bat을 먼저 실행해 주세요."
    exit 1
}
if (-not (Test-Path (Join-Path $UiDir "index.html"))) {
    Write-Host "화면 파일이 없습니다. 설치 파일을 다시 받아 주세요."
    exit 1
}

$env:Path = "$NodeDir;$FfmpegDir;" + $env:Path
$env:SONICSTREAM_LOCATION = "local"
$env:SONICSTREAM_HOME = $Root
$env:SONICSTREAM_UI_DIR = $UiDir
$env:SONICSTREAM_FFMPEG_DIR = $FfmpegDir
$env:YOUTUBE_ALLOW_DIRECT = "true"
$env:PYTHONPATH = $Backend
Remove-Item Env:NEXT_PUBLIC_API_URL -ErrorAction SilentlyContinue

foreach ($envFile in @((Join-Path $Root ".env"), (Join-Path $Backend ".env"))) {
    if (-not (Test-Path $envFile)) { continue }
    Get-Content -LiteralPath $envFile -Encoding UTF8 | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#") -or $line -notmatch "=") { return }
        $name, $value = $line.Split("=", 2)
        $name = $name.Trim()
        $value = $value.Trim().Trim('"').Trim("'")
        if ($name) { Set-Item -Path "Env:$name" -Value $value }
    }
}

function Test-Port([int]$ListenPort) {
    return $null -ne (Get-NetTCPConnection -LocalPort $ListenPort -State Listen -ErrorAction SilentlyContinue)
}

function Test-OurEngine([int]$ListenPort) {
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:$ListenPort/health" -UseBasicParsing -TimeoutSec 2
        if ($health.StatusCode -ne 200 -or $health.Content -notmatch "sonicstream") { return $false }
        $runtime = Invoke-RestMethod -Uri "http://127.0.0.1:$ListenPort/api/runtime" -TimeoutSec 2
        $home = [string]$runtime.home
        if (-not $home) { return $false }
        return ((Resolve-Path $home).Path -eq (Resolve-Path $Root).Path)
    } catch {
        return $false
    }
}

function Get-DesktopWindowBox([int]$WantW, [int]$WantH) {
    if (-not ("SsWorkArea" -as [type])) {
        Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
public static class SsWorkArea {
  [StructLayout(LayoutKind.Sequential)]
  public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
  [DllImport("user32.dll")]
  public static extern bool SystemParametersInfo(int action, int zero, ref RECT rect, int winIni);
  [DllImport("user32.dll")]
  public static extern int GetSystemMetrics(int index);
  public static RECT Read() {
    RECT r = new RECT();
    SystemParametersInfo(48, 0, ref r, 0);
    return r;
  }
  public static int ScreenHeight() { return GetSystemMetrics(1); }
}
"@
    }
    $area = [SsWorkArea]::Read()
    $pad = 16
    $chrome = 48
    $taskbar = 48
    $areaW = [Math]::Max(1, $area.Right - $area.Left)
    $areaH = [Math]::Max(1, $area.Bottom - $area.Top)
    $fullH = [SsWorkArea]::ScreenHeight()
    if ($areaH -ge ($fullH - 2)) { $areaH = [Math]::Max(1, $areaH - $taskbar) }
    $w = [Math]::Min($WantW, [Math]::Max(1, $areaW - $pad * 2))
    $h = [Math]::Min($WantH, [Math]::Max(1, $areaH - $pad * 2 - $chrome))
    $x = $area.Left + [Math]::Min(80, [Math]::Max($pad, $areaW - $w - $pad))
    $y = $area.Top + [Math]::Min(40, [Math]::Max($pad, $areaH - $h - $pad - $chrome))
    $workRight = $area.Left + $areaW
    $workBottom = $area.Top + $areaH
    if ($x + $w -gt $workRight - $pad) { $x = $workRight - $pad - $w }
    if ($y + $h + $chrome -gt $workBottom - $pad) { $y = $workBottom - $pad - $chrome - $h }
    if ($x -lt $area.Left + $pad) { $x = $area.Left + $pad }
    if ($y -lt $area.Top + $pad) { $y = $area.Top + $pad }
    return @{ X = [int]$x; Y = [int]$y; W = [int]$w; H = [int]$h }
}

function Open-AppWindow([string]$Url) {
    New-Item -ItemType Directory -Force -Path $ProfileDir | Out-Null
    $box = Get-DesktopWindowBox 1280 800
    $candidates = @(
        "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe",
        "${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe",
        "$env:LOCALAPPDATA\Microsoft\Edge\Application\msedge.exe",
        "$env:ProgramFiles\Google\Chrome\Application\chrome.exe",
        "${env:ProgramFiles(x86)}\Google\Chrome\Application\chrome.exe",
        "$env:LOCALAPPDATA\Google\Chrome\Application\chrome.exe"
    )
    foreach ($exe in $candidates) {
        if (Test-Path $exe) {
            Start-Process -FilePath $exe -ArgumentList @(
                "--app=$Url",
                "--user-data-dir=$ProfileDir",
                "--window-size=$($box.W),$($box.H)",
                "--window-position=$($box.X),$($box.Y)"
            )
            return
        }
    }
    Start-Process $Url
}

if (Test-Port $Port) {
    if (Test-OurEngine $Port) {
        Open-AppWindow "http://127.0.0.1:$Port/"
        exit 0
    }
    Write-Host "포트 $Port 가 다른 프로그램에 사용 중입니다. 그 프로그램을 종료한 뒤 다시 실행해 주세요."
    exit 1
}

$env:ALLOWED_ORIGINS = "http://127.0.0.1:$Port,http://localhost:$Port"
$proc = Start-Process -FilePath $Python -ArgumentList "-m","uvicorn","main:app","--host","127.0.0.1","--port","$Port","--workers","1" -WorkingDirectory $Backend -WindowStyle Hidden -PassThru
Set-Content -Path $PidFile -Value ("{0}`n{1}" -f $proc.Id, $Python) -Encoding ascii

$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    if ($proc.HasExited) { break }
    if (Test-OurEngine $Port) { $ready = $true; break }
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 2
        if ($health.StatusCode -eq 200) { $ready = $true; break }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}

if (-not $ready) {
    if (-not $proc.HasExited) { Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue }
    Remove-Item $PidFile -ErrorAction SilentlyContinue
    Write-Host "프로그램이 준비되지 않았습니다. 다시 실행해 주세요."
    exit 1
}

Open-AppWindow "http://127.0.0.1:$Port/"
