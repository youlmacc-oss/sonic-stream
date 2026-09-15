from __future__ import annotations

import shutil


def js_runtime_status() -> dict[str, bool]:
    return {
        "deno": shutil.which("deno") is not None,
        "node": shutil.which("node") is not None,
    }


def enabled_js_runtimes() -> dict[str, dict[str, str]]:
    status = js_runtime_status()
    runtimes: dict[str, dict[str, str]] = {}
    if status["deno"]:
        runtimes["deno"] = {}
    if status["node"]:
        runtimes["node"] = {}
    return runtimes


def ejs_package_present() -> bool:
    try:
        import yt_dlp_ejs  # noqa: F401
        return True
    except Exception:
        return False
