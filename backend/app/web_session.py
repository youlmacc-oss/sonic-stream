from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import Request, Response

COOKIE = "sonicstream_web"
TTL_SECONDS = 12 * 60 * 60
RETENTION_LABEL = (
    "이 브라우저 세션에만 12시간 보관됩니다. "
    "서버가 다시 시작되거나 시간이 지나면 다시 입력해야 합니다. "
    "다른 방문객과 공유하지 않으며, 서버 .env에 저장하지 않습니다."
)


@dataclass
class WebSession:
    key: str = ""
    openai: str = "no_key"
    openai_label: str = "AI 키 없음"
    expires_at: float = 0.0


_lock = threading.Lock()
_sessions: dict[str, WebSession] = {}


def reset_for_tests() -> None:
    with _lock:
        _sessions.clear()


def _now() -> float:
    return time.time()


def _sweep(now: float | None = None) -> None:
    moment = _now() if now is None else now
    expired = [sid for sid, item in _sessions.items() if item.expires_at <= moment]
    for sid in expired:
        _sessions.pop(sid, None)


def _new_id() -> str:
    return secrets.token_urlsafe(24)


def _touch(item: WebSession, now: float) -> None:
    item.expires_at = now + TTL_SECONDS


def bind(request: Request, response: Response) -> str:
    now = _now()
    incoming = (request.cookies.get(COOKIE) or "").strip()
    with _lock:
        _sweep(now)
        if incoming and incoming in _sessions:
            sid = incoming
            _touch(_sessions[sid], now)
        else:
            sid = _new_id()
            item = WebSession()
            _touch(item, now)
            _sessions[sid] = item
    secure = request.url.scheme == "https"
    response.set_cookie(
        COOKIE,
        sid,
        max_age=TTL_SECONDS,
        httponly=True,
        secure=secure,
        samesite="none" if secure else "lax",
        path="/",
    )
    return sid


def current_id(request: Request) -> str:
    return (request.cookies.get(COOKIE) or "").strip()


def get(sid: str) -> WebSession | None:
    now = _now()
    with _lock:
        _sweep(now)
        item = _sessions.get(sid)
        if item is None or item.expires_at <= now:
            return None
        return item


def remember(sid: str, *, key: str, openai: str, openai_label: str) -> None:
    now = _now()
    with _lock:
        item = _sessions.get(sid) or WebSession()
        if openai == "ready" and key:
            item.key = key
        else:
            item.key = ""
        item.openai = openai
        item.openai_label = openai_label
        _touch(item, now)
        _sessions[sid] = item


def clear(sid: str) -> None:
    with _lock:
        item = _sessions.get(sid)
        if item is None:
            return
        item.key = ""
        item.openai = "no_key"
        item.openai_label = "AI 키 없음"


def key_for(request: Request) -> str:
    item = get(current_id(request))
    if item is None:
        return ""
    return item.key


def status_for_id(sid: str) -> dict[str, str]:
    item = get(sid)
    openai = item.openai if item else "no_key"
    label = item.openai_label if item else "AI 키 없음"
    model = ""
    if openai == "ready":
        from app.ai_search import openai_model

        model = openai_model()
    return {
        "engine": "ok",
        "engine_label": "프로그램 연결됨",
        "search": "ok",
        "search_label": "유튜브 검색 준비됨",
        "openai": openai,
        "openai_label": label,
        "openai_model": model,
        "retention": "session",
        "retention_label": RETENTION_LABEL,
    }


def status_for(request: Request) -> dict[str, str]:
    return status_for_id(current_id(request))


def classify_openai_error(exc: BaseException) -> dict[str, str]:
    name = type(exc).__name__.lower()
    text = str(exc).lower()
    if "auth" in name or "401" in text or "invalid" in text or "incorrect" in text:
        return {"openai": "key_error", "openai_label": "AI 키가 올바르지 않습니다"}
    if "rate" in name or "quota" in text or "429" in text or "insufficient" in text:
        return {"openai": "quota_error", "openai_label": "AI 사용량 한도입니다"}
    return {"openai": "network_error", "openai_label": "AI 네트워크 오류"}


def verify_session_key(key: str) -> dict[str, str]:
    value = (key or "").strip()
    if not value:
        return {"openai": "no_key", "openai_label": "AI 키 없음"}
    try:
        from openai import OpenAI
    except Exception:
        return {"openai": "no_sdk", "openai_label": "AI 모듈 없음"}
    try:
        OpenAI(api_key=value, timeout=12.0).models.list()
    except Exception as exc:
        return classify_openai_error(exc)
    return {"openai": "ready", "openai_label": "AI 연결됨"}
