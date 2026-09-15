from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urlparse, urlencode, urlunparse

SCHEMA_VERSION = 2

SECRET_RE = re.compile(
    r"(?i)("
    r"(?:set-)?cookie\s*[:=][^\n;]+"
    r"|authorization\s*[:=]\s*\S+"
    r"|https?://[^/\s:]+:[^@\s]+@"
    r"|po[_\s-]*token\s*[:=]\s*\S+"
    r"|visitor_data\s*[:=]\s*\S+"
    r"|login_info\s*[:=]\s*\S+"
    r"|admin[_-]?token\s*[:=]\s*\S+"
    r"|api[_-]?key\s*[:=]\s*\S+"
    r"|sid=[^&\s]+|hsid=[^&\s]+|ssid=[^&\s]+"
    r"|signature=[^&\s]+|n=[A-Za-z0-9_\-]{8,}"
    r"|googlevideo\.com/videoplayback[^\s]+"
    r")"
)

SENSITIVE_KEYS = {
    "cookie",
    "cookies",
    "set-cookie",
    "authorization",
    "proxy",
    "po_token",
    "potoken",
    "visitor_data",
    "login_info",
    "admin_token",
    "debug_backlog_token",
    "api_key",
    "password",
    "passwd",
    "secret",
}

HTTP_STATUS_RE = re.compile(r"\b(?:http(?:\s*error)?|status)\s*[:=]?\s*(\d{3})\b|\b([1-5]\d{2})\b", re.I)
YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?.*?v=|embed/|shorts/|live/|music/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)
ALLOWED_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
}


def mask_text(value: str, limit: int = 800) -> str:
    cleaned = SECRET_RE.sub("[redacted]", value)
    return cleaned[:limit]


def _key_sensitive(key: str) -> bool:
    lowered = key.lower().replace("-", "_")
    return lowered in SENSITIVE_KEYS or any(part in lowered for part in ("token", "cookie", "password", "secret", "authorization"))


def mask_value(value: Any, *, limit: int = 800, depth: int = 0) -> Any:
    if depth > 6:
        return "[redacted]"
    if value is None or isinstance(value, (int, float, bool)):
        return value
    if isinstance(value, str):
        return mask_text(value, limit)
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in list(value.items())[:80]:
            name = str(key)
            out[name] = "[redacted]" if _key_sensitive(name) else mask_value(item, limit=limit, depth=depth + 1)
        return out
    if isinstance(value, (list, tuple)):
        return [mask_value(item, limit=limit, depth=depth + 1) for item in list(value)[:50]]
    return mask_text(str(value), limit)


def sanitize_url(url: str | None) -> str | None:
    if not url:
        return None
    match = YOUTUBE_ID_RE.search(url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    host = (parsed.hostname or "").lower()
    if not host:
        return None
    if host not in ALLOWED_HOSTS:
        return f"{parsed.scheme or 'https'}://{host}/"
    query = parse_qs(parsed.query)
    keep = {}
    if "v" in query and query["v"]:
        keep["v"] = [query["v"][0][:11]]
    clean = parsed._replace(query=urlencode(keep, doseq=True), fragment="", params="")
    return urlunparse(clean)


def extract_http_status(text: str | None) -> int | None:
    if not text:
        return None
    match = HTTP_STATUS_RE.search(text)
    if not match:
        return None
    raw = match.group(1) or match.group(2)
    try:
        status = int(raw)
    except ValueError:
        return None
    if 100 <= status <= 599:
        return status
    return None


def video_id_from_url(url: str | None) -> str | None:
    if not url:
        return None
    match = YOUTUBE_ID_RE.search(url)
    return match.group(1) if match else None


def diagnostic_record(
    *,
    job_id: str | None,
    attempt: int,
    stage: str,
    route_alias: str | None,
    client: str | None,
    elapsed_ms: int,
    code: str,
    error_type: str,
    error_message: str,
) -> dict[str, Any]:
    return {
        "job_id": job_id,
        "attempt": attempt,
        "stage": stage,
        "route_alias": route_alias,
        "client": client,
        "elapsed_ms": elapsed_ms,
        "code": code,
        "error_type": error_type,
        "error_message": mask_text(error_message, 400),
    }
