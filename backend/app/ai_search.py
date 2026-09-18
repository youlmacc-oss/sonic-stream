from __future__ import annotations

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.file_registry import data_dir
from app.ytdlp_engine import YTSEARCH_LIMIT, normalize_search_query, search_ytsearch

logger = logging.getLogger("sonicstream.ai_search")

DEFAULT_MODEL = "gpt-4o-mini"
MAX_PROMPT = 400
KEYWORD_LIMIT = 2
RESULT_LIMIT = YTSEARCH_LIMIT


class AiSearchError(Exception):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def openai_model() -> str:
    return (os.getenv("OPENAI_MODEL") or DEFAULT_MODEL).strip() or DEFAULT_MODEL


def openai_api_key() -> str:
    return (os.getenv("OPENAI_API_KEY") or "").strip()


def _key_fingerprint(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


def _status_path() -> Path:
    return data_dir() / "openai-status.json"


def _load_last_check() -> dict[str, Any]:
    try:
        payload = json.loads(_status_path().read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _save_last_check(payload: dict[str, Any]) -> None:
    path = _status_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def verify_openai_key(key: str | None = None) -> dict[str, str]:
    value = (key or openai_api_key()).strip()
    try:
        from openai import OpenAI
    except Exception:
        result = {"openai": "no_sdk", "openai_label": "AI 모듈 없음"}
        _save_last_check({**result, "fingerprint": _key_fingerprint(value) if value else ""})
        return result
    if not value:
        return {"openai": "no_key", "openai_label": "AI 키 없음"}
    state = {"openai": "network_error", "openai_label": "AI 네트워크 오류"}
    try:
        client = OpenAI(api_key=value, timeout=12.0)
        client.models.list()
        state = {"openai": "ready", "openai_label": "AI 연결됨"}
    except Exception as exc:
        name = type(exc).__name__.lower()
        text = str(exc).lower()
        if "auth" in name or "401" in text or "invalid" in text:
            state = {"openai": "key_error", "openai_label": "AI 키가 올바르지 않습니다"}
        elif "rate" in name or "quota" in text or "429" in text or "insufficient" in text:
            state = {"openai": "quota_error", "openai_label": "AI 사용량 한도입니다"}
        else:
            state = {"openai": "network_error", "openai_label": "AI 네트워크 오류"}
    _save_last_check(
        {
            **state,
            "fingerprint": _key_fingerprint(value),
            "checked_at": datetime.now(timezone.utc).isoformat(),
        }
    )
    return state


def connection_status() -> dict[str, str]:
    key = openai_api_key()
    try:
        import openai  # noqa: F401
        sdk_ok = True
    except Exception:
        sdk_ok = False
    if not key:
        openai_state = "no_key"
        openai_label = "AI 키 없음"
    elif not sdk_ok:
        openai_state = "no_sdk"
        openai_label = "AI 모듈 없음"
    else:
        last = _load_last_check()
        if last.get("fingerprint") == _key_fingerprint(key) and last.get("openai"):
            openai_state = str(last.get("openai"))
            openai_label = str(last.get("openai_label") or "AI 상태")
        else:
            openai_state = "configured"
            openai_label = "AI 키 저장됨"
    return {
        "engine": "ok",
        "engine_label": "프로그램 연결됨",
        "search": "ok",
        "search_label": "유튜브 검색 준비됨",
        "openai": openai_state,
        "openai_label": openai_label,
        "openai_model": openai_model() if openai_state == "ready" else "",
    }


def normalize_prompt(raw: str) -> str:
    text = " ".join((raw or "").split())
    if not text or len(text) > MAX_PROMPT:
        raise ValueError("INVALID_URL")
    if "\x00" in text:
        raise ValueError("INVALID_URL")
    return text


def _parse_plan(raw: str, fallback_prompt: str) -> tuple[str, list[str]]:
    reply = "이 이야기에 맞는 영상을 찾아 봤습니다."
    keywords: list[str] = []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {}
    if isinstance(payload, dict):
        maybe_reply = str(payload.get("reply") or "").strip()
        if maybe_reply:
            reply = maybe_reply[:400]
        raw_keywords = payload.get("keywords")
        if isinstance(raw_keywords, str):
            raw_keywords = re.split(r"[,/\n]+", raw_keywords)
        if isinstance(raw_keywords, list):
            for item in raw_keywords:
                try:
                    keywords.append(normalize_search_query(str(item)))
                except ValueError:
                    continue
                if len(keywords) >= KEYWORD_LIMIT:
                    break
    if not keywords:
        try:
            keywords.append(normalize_search_query(fallback_prompt))
        except ValueError:
            pass
    unique: list[str] = []
    seen: set[str] = set()
    for word in keywords:
        key = word.casefold()
        if key in seen:
            continue
        seen.add(key)
        unique.append(word)
    return reply, unique[:KEYWORD_LIMIT]


def plan_search(prompt: str, history: list[dict[str, str]] | None = None) -> tuple[str, list[str]]:
    key = openai_api_key()
    if not key:
        raise AiSearchError("AI_UNAVAILABLE")
    try:
        from openai import OpenAI
    except Exception as exc:
        logger.info("OpenAI SDK missing: %s", exc)
        raise AiSearchError("AI_UNAVAILABLE") from exc
    client = OpenAI(api_key=key)
    system = (
        "You are SonicStream's Korean video search assistant. "
        "Turn the latest user request into YouTube search keywords. "
        "Use earlier turns only as context. "
        "Reply with JSON only: {\"reply\": string, \"keywords\": [string]}. "
        "reply is 1-3 natural Korean sentences, conversational, no markdown. "
        "keywords has 1 or 2 concrete YouTube search phrases, no hashtags."
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system}]
    for turn in (history or [])[-6:]:
        role = str(turn.get("role") or "")
        content = str(turn.get("content") or "").strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content[:400]})
    messages.append({"role": "user", "content": prompt})
    try:
        response = client.chat.completions.create(
            model=openai_model(),
            temperature=0.4,
            max_tokens=280,
            response_format={"type": "json_object"},
            messages=messages,
        )
    except Exception as exc:
        logger.info("OpenAI search plan failed: %s", type(exc).__name__)
        raise AiSearchError("AI_FAILED") from exc
    content = ""
    try:
        content = (response.choices[0].message.content or "").strip()
    except Exception:
        content = ""
    return _parse_plan(content, prompt)


def collect_ytsearch_hits(keywords: list[str], limit: int = RESULT_LIMIT) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()
    for keyword in keywords:
        try:
            hits = search_ytsearch(keyword, limit)
        except Exception as exc:
            logger.info("ytsearch missed for planned keyword: %s", type(exc).__name__)
            continue
        for hit in hits:
            url = str(hit.get("url") or "")
            if not url or url in seen:
                continue
            seen.add(url)
            items.append(hit)
            if len(items) >= limit:
                return items
    return items


def run_ai_search(prompt: str, history: list[dict[str, str]] | None = None) -> dict[str, Any]:
    cleaned = normalize_prompt(prompt)
    reply, keywords = plan_search(cleaned, history)
    items = collect_ytsearch_hits(keywords, RESULT_LIMIT)
    if not items and keywords:
        try:
            items = search_ytsearch(cleaned, RESULT_LIMIT)
        except Exception:
            items = []
    return {"reply": reply, "keywords": keywords, "items": items}
