@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SonicStream을 이 PC에 설치합니다.
echo 받은 영상은 지워지지 않습니다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install-desktop.ps1"
if errorlevel 1 pause
