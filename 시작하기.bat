@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SonicStream 내 PC 다운로드
echo 쿠키 파일을 내보낼 필요는 없습니다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1"
if errorlevel 1 pause
