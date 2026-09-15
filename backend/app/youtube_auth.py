from __future__ import annotations

import hashlib
import logging
import os
import stat
import tempfile
import threading
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger("sonicstream.youtube")

CookieState = Literal["missing", "invalid_format", "file_present"]

_COOKIE_RUNTIME = Path(tempfile.gettempdir()) / "sonic_youtube_cookies.txt"
_lock = threading.Lock()
_cached_hash: str | None = None
_cached_path: str | None = None
_impersonate_cache: Any | None = False


def _looks_like_netscape(text: str) -> bool:
    stripped = text.lstrip()
    if stripped.startswith("# Netscape") or stripped.startswith("# HTTP Cookie File"):
        return True
    for line in stripped.splitlines():
        if not line or line.startswith("#"):
            continue
        return line.count("\t") >= 5
    return False


def _is_placeholder(text: str) -> bool:
    cleaned = text.strip().strip("\"'")
    if not cleaned:
        return True
    lowered = cleaned.lower()
    if lowered in {"*", "null", "none", "undefined", "changeme", "change-me", "your_cookies_here", "todo"}:
        return True
    return set(cleaned) <= {"*", ".", "-", " "}


def _cookie_env_text() -> str:
    raw = (os.getenv("YOUTUBE_COOKIES") or "").strip()
    if _is_placeholder(raw):
        return ""
    return raw.replace("\\n", "\n")


def cookie_state() -> CookieState:
    path = (os.getenv("YOUTUBE_COOKIES_FILE") or "").strip()
    if path:
        if _is_placeholder(path) or not Path(path).exists():
            return "missing"
        try:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return "missing"
        return "file_present" if _looks_like_netscape(text) else "invalid_format"

    text = _cookie_env_text()
    if not text:
        return "missing"
    return "file_present" if _looks_like_netscape(text) else "invalid_format"


def resolve_cookiefile() -> str | None:
    global _cached_hash, _cached_path
    if cookie_state() != "file_present":
        return None
    path = (os.getenv("YOUTUBE_COOKIES_FILE") or "").strip()
    if path and not _is_placeholder(path) and Path(path).exists() and _looks_like_netscape(Path(path).read_text(encoding="utf-8", errors="replace")):
        return path

    text = _cookie_env_text()
    if not text or not _looks_like_netscape(text):
        return None
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with _lock:
        if _cached_hash == digest and _cached_path and Path(_cached_path).exists():
            return _cached_path
        try:
            _COOKIE_RUNTIME.write_text(text, encoding="utf-8")
            _COOKIE_RUNTIME.chmod(stat.S_IRUSR | stat.S_IWUSR)
            _cached_hash = digest
            _cached_path = str(_COOKIE_RUNTIME)
            return _cached_path
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
    global _impersonate_cache
    raw = (os.getenv("YOUTUBE_IMPERSONATE") or "chrome").strip()
    if raw.lower() in {"0", "false", "off", "none"}:
        return None
    if _impersonate_cache is not False:
        return _impersonate_cache
    try:
        import curl_cffi  # noqa: F401
        from yt_dlp.networking.impersonate import ImpersonateTarget

        _impersonate_cache = ImpersonateTarget.from_str(raw.lower())
        return _impersonate_cache
    except Exception as exc:
        logger.info("TLS impersonation unavailable: %s", exc)
        _impersonate_cache = None
        return None


def has_cookies() -> bool:
    return cookie_state() == "file_present"


def auth_status() -> dict[str, object]:
    return {
        "cookies": cookie_state(),
        "proxy": resolve_proxy() is not None,
        "impersonate": resolve_impersonate() is not None,
    }


def apply_youtube_auth(
    opts: dict[str, Any],
    proxy: str | None = None,
    use_cookies: bool = True,
    use_impersonate: bool = True,
) -> dict[str, Any]:
    if use_cookies:
        cookiefile = resolve_cookiefile()
        if cookiefile:
            opts["cookiefile"] = cookiefile
    if proxy:
        opts["proxy"] = proxy
    if use_impersonate:
        impersonate = resolve_impersonate()
        if impersonate is not None:
            opts["impersonate"] = impersonate
            opts.pop("user_agent", None)
            opts.pop("http_headers", None)
    else:
        opts.pop("impersonate", None)
    return opts


def log_auth_status() -> None:
    status = auth_status()
    logger.info(
        "YouTube auth: cookies=%s proxy=%s impersonate=%s",
        status["cookies"],
        status["proxy"],
        status["impersonate"],
    )
