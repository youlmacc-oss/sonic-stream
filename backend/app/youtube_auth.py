from __future__ import annotations

import logging
import os
import tempfile
from pathlib import Path
from typing import Any

logger = logging.getLogger("sonicstream.youtube")

_COOKIE_RUNTIME = Path(tempfile.gettempdir()) / "sonic_youtube_cookies.txt"


def resolve_cookiefile() -> str | None:
    path = (os.getenv("YOUTUBE_COOKIES_FILE") or "").strip()
    if path and Path(path).exists():
        return path

    raw = (os.getenv("YOUTUBE_COOKIES") or "").strip()
    if not raw:
        return None

    text = raw.replace("\\n", "\n")
    try:
        _COOKIE_RUNTIME.write_text(text, encoding="utf-8")
        return str(_COOKIE_RUNTIME)
    except OSError as exc:
        logger.warning("Could not write YouTube cookies: %s", exc)
        return None


def resolve_proxy() -> str | None:
    for key in ("YOUTUBE_PROXY", "HTTPS_PROXY", "HTTP_PROXY"):
        value = (os.getenv(key) or "").strip()
        if value:
            return value
    return None


def resolve_impersonate() -> Any | None:
    raw = (os.getenv("YOUTUBE_IMPERSONATE") or "chrome").strip()
    if raw.lower() in {"0", "false", "off", "none"}:
        return None
    try:
        import curl_cffi  # noqa: F401
        from yt_dlp.networking.impersonate import ImpersonateTarget

        return ImpersonateTarget.from_str(raw.lower())
    except Exception as exc:
        logger.info("TLS impersonation unavailable: %s", exc)
        return None


def has_cookies() -> bool:
    return resolve_cookiefile() is not None


def auth_status() -> dict[str, bool]:
    return {
        "cookies": has_cookies(),
        "proxy": resolve_proxy() is not None,
        "impersonate": resolve_impersonate() is not None,
    }


def apply_youtube_auth(opts: dict[str, Any]) -> dict[str, Any]:
    cookiefile = resolve_cookiefile()
    if cookiefile:
        opts["cookiefile"] = cookiefile

    proxy = resolve_proxy()
    if proxy:
        opts["proxy"] = proxy

    impersonate = resolve_impersonate()
    if impersonate is not None:
        opts["impersonate"] = impersonate

    return opts


def log_auth_status() -> None:
    status = auth_status()
    logger.info(
        "YouTube auth: cookies=%s proxy=%s impersonate=%s",
        status["cookies"],
        status["proxy"],
        status["impersonate"],
    )
    if not status["cookies"] and not status["proxy"]:
        logger.warning(
            "Render datacenter IPs are often bot-gated. "
            "Set YOUTUBE_COOKIES or YOUTUBE_PROXY to unlock downloads.",
        )
