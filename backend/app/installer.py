from __future__ import annotations

import os
from pathlib import Path

INSTALLER_NAME = "SonicStream-Windows.zip"
DEFAULT_PUBLIC_URL = (
    "https://github.com/youlmacc-oss/sonic-stream/releases/download/windows/SonicStream-Windows.zip"
)


def installer_file() -> Path | None:
    raw = (os.getenv("SONICSTREAM_INSTALLER_PATH") or "").strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    else:
        here = Path(__file__).resolve()
        repo_root = here.parents[2] if len(here.parents) > 2 else here.parents[1].parent
        candidates.append(repo_root / "dist" / INSTALLER_NAME)
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        return resolved
    return None


def installer_redirect_url() -> str | None:
    raw = (os.getenv("SONICSTREAM_INSTALLER_URL") or "").strip()
    return raw or None


def installer_public_url(request_base: str | None = None) -> str:
    redirect = installer_redirect_url()
    if redirect:
        return redirect
    if installer_file() and request_base:
        return f"{request_base.rstrip('/')}/api/desktop/installer"
    return DEFAULT_PUBLIC_URL


def installer_info(request_base: str | None = None) -> dict[str, object]:
    path = installer_file()
    url = installer_public_url(request_base)
    return {
        "available": path is not None,
        "filename": INSTALLER_NAME,
        "bytes": path.stat().st_size if path is not None else None,
        "url": url,
        "setup_url": f"{request_base.rstrip('/')}/api/desktop/setup" if request_base else "/api/desktop/setup",
        "setup_name": "SonicStream-설치.bat",
    }


def setup_batch(zip_url: str) -> str:
    escaped = zip_url.replace("'", "''")
    return (
        "@echo off\r\n"
        "chcp 65001 >nul\r\n"
        "echo SonicStream 설치를 시작합니다.\r\n"
        "echo 동의한 뒤 받은 이 파일을 연 것입니다.\r\n"
        "echo 설치 파일을 내려받는 동안 이 창을 닫지 마세요.\r\n"
        "powershell -NoProfile -ExecutionPolicy Bypass -Command ^\r\n"
        "  \"$ErrorActionPreference='Stop'; "
        f"$url='{escaped}'; "
        "$work=Join-Path $env:TEMP 'SonicStream-Setup'; "
        "New-Item -ItemType Directory -Force -Path $work | Out-Null; "
        "$zip=Join-Path $work 'SonicStream-Windows.zip'; "
        "Write-Host '설치 파일을 받는 중입니다.'; "
        "Invoke-WebRequest -Uri $url -OutFile $zip -UseBasicParsing; "
        "$extract=Join-Path $work 'app'; "
        "if (Test-Path $extract) { Remove-Item -Recurse -Force $extract }; "
        "Expand-Archive -Path $zip -DestinationPath $extract -Force; "
        "$inner=$extract; "
        "if (Test-Path (Join-Path $extract 'SonicStream-Windows\\설치하기.bat')) { "
        "$inner=Join-Path $extract 'SonicStream-Windows' }; "
        "if (-not (Test-Path (Join-Path $inner 'install-desktop.ps1'))) { "
        "$dir=Get-ChildItem $extract -Directory | Select-Object -First 1; "
        "if ($dir) { $inner=$dir.FullName } }; "
        "if (-not (Test-Path (Join-Path $inner 'install-desktop.ps1'))) { "
        "throw '설치 파일을 풀지 못했습니다.' }; "
        "Write-Host '이 컴퓨터에 설치합니다.'; "
        "& (Join-Path $inner 'install-desktop.ps1')\"\r\n"
        "if errorlevel 1 pause\r\n"
    )
