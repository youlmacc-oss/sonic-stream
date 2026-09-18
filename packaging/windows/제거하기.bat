@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SonicStream 프로그램만 제거합니다.
echo 다운로드 폴더의 영상은 그대로 둡니다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0uninstall-desktop.ps1"
if errorlevel 1 pause
