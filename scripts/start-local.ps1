$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
. (Join-Path $PSScriptRoot "package-fingerprint.ps1")
if (-not (Test-Path (Join-Path $Root "backend\main.py"))) {
    $Root = Split-Path -Parent $MyInvocation.MyCommand.Path
    $Root = Split-Path -Parent $Root
}

$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"
$PortApi = 8000
$PortUi = 3000

function Test-Port([int]$Port) {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return $null -ne $listener
}

Write-Host "SonicStream 내 PC 다운로드를 준비합니다."
Write-Host "프로젝트: $Root"
Write-Host "이 실행은 개발용입니다. 설치 ZIP은 만들지 않습니다."
try {
    $fp = Get-SonicStreamSourceFingerprint -Root $Root
    if (-not (Test-SonicStreamPackageFresh -Root $Root -Fingerprint $fp)) {
        Write-Host "경고: 설치 ZIP이 현재 소스와 다릅니다. 다른 PC에 주려면 다른PC에설치하기.bat을 다시 실행하세요."
    } else {
        Write-Host "설치 ZIP 지문이 현재 소스와 같습니다."
    }
} catch {
    Write-Host "설치 ZIP 지문을 비교하지 못했습니다. 배포 전에 다른PC에설치하기.bat을 실행하세요."
}

if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Test-Path $VenvPython)) {
    Write-Host "Python이 필요합니다. https://www.python.org/downloads/ 에서 설치한 뒤 다시 실행해 주세요."
    exit 1
}

if (-not (Test-Path $VenvPython)) {
    Write-Host "가상환경을 만들고 패키지를 설치합니다..."
    Push-Location $Backend
    python -m venv .venv
    & $VenvPython -m pip install --upgrade pip
    & $VenvPython -m pip install -r requirements.txt
    Pop-Location
}

if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js가 필요합니다. https://nodejs.org/ 에서 설치한 뒤 다시 실행해 주세요."
    exit 1
}

if (-not (Test-Path (Join-Path $Frontend "node_modules"))) {
    Write-Host "화면 패키지를 설치합니다..."
    Push-Location $Frontend
    npm install
    Pop-Location
}

$env:SONICSTREAM_LOCATION = "local"
$env:ALLOWED_ORIGINS = "http://127.0.0.1:$PortUi,http://localhost:$PortUi,http://127.0.0.1:$PortApi,http://localhost:$PortApi"
$env:YOUTUBE_ALLOW_DIRECT = "true"
Remove-Item Env:NEXT_PUBLIC_API_URL -ErrorAction SilentlyContinue

if (Test-Port $PortApi) {
    Write-Host "이미 $PortApi 포트가 사용 중입니다. 기존 SonicStream이 켜져 있으면 그 창을 사용하세요."
} else {
    Write-Host "다운로드 엔진을 시작합니다..."
    Start-Process -FilePath $VenvPython -ArgumentList "-m","uvicorn","main:app","--host","127.0.0.1","--port","$PortApi","--workers","1" -WorkingDirectory $Backend -WindowStyle Minimized
}

$ready = $false
for ($i = 0; $i -lt 40; $i++) {
    try {
        $health = Invoke-WebRequest -Uri "http://127.0.0.1:$PortApi/health" -UseBasicParsing -TimeoutSec 2
        if ($health.StatusCode -eq 200) { $ready = $true; break }
    } catch {
        Start-Sleep -Milliseconds 500
    }
}
if (-not $ready) {
    Write-Host "엔진이 준비되지 않았습니다. 이 창을 닫고 시작하기.bat을 다시 실행해 주세요."
    exit 1
}

if (-not (Test-Port $PortUi)) {
    Write-Host "화면을 시작합니다..."
    Start-Process -FilePath "npm" -ArgumentList "run","dev","--","--hostname","127.0.0.1","--port","$PortUi" -WorkingDirectory $Frontend -WindowStyle Minimized
}

Start-Sleep -Seconds 2
Start-Process "http://127.0.0.1:$PortUi"
Write-Host ""
Write-Host "브라우저가 열리면 주소를 붙여넣고 다운로드를 누르세요."
Write-Host "종료하려면 이 창을 닫지 말고, 작업 표시줄의 Python/Node 창을 닫으면 됩니다."
Write-Host "쿠키 파일을 내보낼 필요는 없습니다."
Read-Host "이 창은 열어 두세요. 종료하려면 Enter"
