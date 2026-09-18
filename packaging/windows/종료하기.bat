@echo off
chcp 65001 >nul
cd /d "%~dp0"
if exist "%~dp0runtime.pid" (
  for /f %%i in (%~dp0runtime.pid) do taskkill /PID %%i /F >nul 2>&1
  del /f /q "%~dp0runtime.pid" >nul 2>&1
)
echo SonicStream을 종료했습니다. 받은 파일은 그대로 있습니다.
pause
