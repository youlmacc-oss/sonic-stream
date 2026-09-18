@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo 기본설계: 설치 ZIP은 프로그램과 항상 같아야 합니다.
echo 지금 소스(화면/엔진/안내문)를 다시 빌드해 설치 파일을 만듭니다.
echo 예전 ZIP을 재사용하지 않습니다.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\package-windows.ps1"
if errorlevel 1 (
  echo 설치 파일 만들기에 실패했습니다.
  pause
  exit /b 1
)
explorer /select,"%~dp0dist\SonicStream-Windows.zip"
echo.
echo 최신 ZIP을 USB나 클라우드로 다른 PC에 복사한 뒤 압축을 풀고 설치하기.bat을 실행하세요.
pause
