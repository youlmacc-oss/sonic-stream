from __future__ import annotations

import os
import shutil
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from importlib.metadata import PackageNotFoundError, version as pkg_version
from typing import Any

from app.limiter import limiter
from app.pot import pot_plugin_loaded, pot_status
from app.routes import route_status
from app.runtime import ejs_package_present, js_runtime_status
from app.youtube_auth import cookie_state

_SNAPSHOT: dict[str, Any] | None = None
_INSTANCE_ID = (os.getenv("RENDER_INSTANCE_ID") or os.getenv("INSTANCE_ID") or uuid.uuid4().hex[:12]).strip()


def instance_id() -> str:
    return _INSTANCE_ID


def _pkg(name: str) -> str:
    try:
        return pkg_version(name)
    except PackageNotFoundError:
        return "unknown"
    except Exception:
        return "unknown"


def _command_version(binary: str) -> str:
    path = shutil.which(binary)
    if path is None:
        return "missing"
    try:
        completed = subprocess.run(
            [path, "--version"],
            capture_output=True,
            check=False,
            timeout=4,
            text=True,
        )
        line = (completed.stdout or completed.stderr or "").splitlines()
        return line[0].strip()[:120] if line else "unknown"
    except Exception:
        return "unknown"


def _deploy_version() -> str:
    for key in ("RENDER_GIT_COMMIT", "GITHUB_SHA", "SOURCE_VERSION", "GIT_COMMIT"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value[:40]
    return "unknown"


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def capture_snapshot() -> dict[str, Any]:
    global _SNAPSHOT
    runtimes = js_runtime_status()
    pot = pot_status()
    snapshot = {
        "snapshot_id": uuid.uuid4().hex,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "deploy_version": _deploy_version(),
        "instance_id": instance_id(),
        "python": sys.version.split()[0],
        "yt_dlp": _pkg("yt-dlp"),
        "yt_dlp_ejs": _pkg("yt-dlp-ejs") if ejs_package_present() else "missing",
        "curl_cffi": _pkg("curl_cffi"),
        "js_runtimes": {
            "deno": _command_version("deno") if runtimes["deno"] else "missing",
            "node": _command_version("node") if runtimes["node"] else "missing",
        },
        "ffmpeg": _command_version("ffmpeg"),
        "pot": {
            "provider": "bgutil-http" if pot_plugin_loaded() else "none",
            "plugin": pot["plugin"],
            "configured": pot["configured"],
            "reachable": pot["reachable"],
            "version": _pkg("bgutil-ytdlp-pot-provider") if pot_plugin_loaded() else "missing",
        },
        "cookies": {
            "state": cookie_state(),
            "mode": (os.getenv("YOUTUBE_COOKIE_MODE") or "anonymous_first").strip().lower(),
        },
        "routes": [{"alias": item["alias"], "has_proxy": item["has_proxy"]} for item in route_status()],
        "settings": {
            "max_concurrent_downloads": limiter.max_active,
            "max_download_queue": limiter.max_queue,
            "max_job_attempts": _int_env("MAX_JOB_ATTEMPTS", 4),
            "max_rate_limit_waits": _int_env("MAX_RATE_LIMIT_WAITS", 2),
            "max_route_switches": _int_env("MAX_ROUTE_SWITCHES", 1),
            "job_timeout_seconds": _int_env("JOB_TIMEOUT_SECONDS", 720),
            "log_process_note": "in-memory-single-process",
        },
    }
    _SNAPSHOT = snapshot
    return snapshot


def current_snapshot() -> dict[str, Any]:
    return _SNAPSHOT or capture_snapshot()


def snapshot_id() -> str:
    return str(current_snapshot()["snapshot_id"])
