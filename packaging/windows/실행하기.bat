@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SonicStream을 이 PC에서 시작합니다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run-desktop.ps1"
if errorlevel 1 pause
