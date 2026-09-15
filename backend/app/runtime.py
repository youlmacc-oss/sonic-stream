from __future__ import annotations

import shutil


def js_runtime_status() -> dict[str, bool]:
    return {
        "deno": shutil.which("deno") is not None,
        "node": shutil.which("node") is not None,
    }


def enabled_js_runtimes() -> dict[str, dict[str, str]]:
    status = js_runtime_status()
    # Prefer Node when both exist; cookie-free local success used Node only.
    if status["node"]:
        return {"node": {}}
    if status["deno"]:
        return {"deno": {}}
    return {}


def ejs_package_present() -> bool:
    try:
        import yt_dlp_ejs  # noqa: F401
        return True
    except Exception:
        return False
