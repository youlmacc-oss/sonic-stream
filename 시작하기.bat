@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo SonicStream 개발용 실행입니다.
echo 일반 사용자는 설치 파일의 바탕화면 아이콘을 사용하세요.
echo 소스를 바꾼 뒤 다른 PC에 줄 ZIP은 이 파일이 아니라 다른PC에설치하기.bat으로 다시 만듭니다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-local.ps1"
if errorlevel 1 pause
