from __future__ import annotations

import json
import logging
import re
import time
import urllib.request
from typing import Any

from yt_dlp import YoutubeDL

from app.ytdlp_engine import base_ydl_opts, canonicalize_media_url, validate_url

logger = logging.getLogger("sonicstream.transcript")

PREFERRED_LANGS = ("ko", "ko-KR", "ko-orig", "en", "en-US", "en-orig")
PREFERRED_EXTS = ("json3", "vtt")
SUPPORTED_EXTS = {"json3", "json", "vtt", "webvtt"}
CACHE_TTL_SEC = 30 * 60
CACHE_MAX = 32
LINE_LIMIT = 800

_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_WEBVTT_TS = re.compile(
    r"(?P<start>(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3})\s+-->\s+(?:\d{1,2}:)?\d{1,2}:\d{2}[.,]\d{3}"
)


def parse_json3_captions(raw: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    events = payload.get("events") if isinstance(payload, dict) else None
    if not isinstance(events, list):
        return []
    lines: list[dict[str, Any]] = []
    for event in events:
        if not isinstance(event, dict):
            continue
        segs = event.get("segs")
        if not isinstance(segs, list):
            continue
        text = "".join(str(part.get("utf8") or "") for part in segs if isinstance(part, dict))
        text = " ".join(text.replace("\n", " ").split())
        if not text:
            continue
        start_ms = event.get("tStartMs") or 0
        try:
            start = max(0.0, float(start_ms) / 1000.0)
        except (TypeError, ValueError):
            start = 0.0
        lines.append({"start": start, "text": text})
        if len(lines) >= LINE_LIMIT:
            break
    return lines


def _timestamp_to_seconds(value: str) -> float:
    cleaned = value.replace(",", ".")
    parts = cleaned.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except (TypeError, ValueError):
        return 0.0
    return 0.0


def parse_vtt_captions(raw: str) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    blocks = re.split(r"\n\s*\n", raw.replace("\r\n", "\n"))
    for block in blocks:
        match = _WEBVTT_TS.search(block)
        if not match:
            continue
        body = []
        for row in block.splitlines():
            if "-->" in row or row.strip().isdigit() or row.strip().upper() == "WEBVTT":
                continue
            if row.startswith("NOTE") or row.startswith("STYLE") or row.startswith("KIND"):
                continue
            cleaned = re.sub(r"<[^>]+>", "", row).strip()
            if cleaned:
                body.append(cleaned)
        text = " ".join(" ".join(body).split())
        if not text:
            continue
        lines.append({"start": _timestamp_to_seconds(match.group("start")), "text": text})
        if len(lines) >= LINE_LIMIT:
            break
    return lines


def _parse_caption_body(raw: str, ext: str) -> list[dict[str, Any]]:
    kind = (ext or "").lower()
    if kind in {"json3", "json"} or raw.lstrip().startswith("{"):
        lines = parse_json3_captions(raw)
        if lines:
            return lines
    if kind in {"vtt", "webvtt"} or "WEBVTT" in raw[:64]:
        return parse_vtt_captions(raw)
    return parse_json3_captions(raw) or parse_vtt_captions(raw)


def pick_caption_track(info: dict[str, Any]) -> tuple[str, bool, dict[str, Any]] | None:
    groups = (
        (False, info.get("subtitles") if isinstance(info.get("subtitles"), dict) else {}),
        (True, info.get("automatic_captions") if isinstance(info.get("automatic_captions"), dict) else {}),
    )
    for automatic, mapping in groups:
        langs = [name for name in PREFERRED_LANGS if name in mapping]
        langs.extend(name for name in mapping if name not in langs)
        for lang in langs:
            tracks = mapping.get(lang)
            if not isinstance(tracks, list):
                continue
            by_ext = {str(track.get("ext") or "").lower(): track for track in tracks if isinstance(track, dict)}
            for ext in PREFERRED_EXTS:
                track = by_ext.get(ext)
                if track and (track.get("url") or track.get("data")):
                    return str(lang), automatic, track
            for track in tracks:
                if not isinstance(track, dict) or not (track.get("url") or track.get("data")):
                    continue
                ext = str(track.get("ext") or "").lower()
                if ext in SUPPORTED_EXTS:
                    return str(lang), automatic, track
    return None


def _fetch_caption_text(url: str) -> str:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(request, timeout=12) as response:
        return response.read().decode("utf-8", "replace")


def _cache_get(url: str) -> dict[str, Any] | None:
    item = _cache.get(url)
    if item is None:
        return None
    stamped, payload = item
    if time.time() - stamped > CACHE_TTL_SEC:
        _cache.pop(url, None)
        return None
    return payload


def _cache_put(url: str, payload: dict[str, Any]) -> None:
    _cache[url] = (time.time(), payload)
    extra = len(_cache) - CACHE_MAX
    if extra > 0:
        oldest = sorted(_cache.items(), key=lambda item: item[1][0])[:extra]
        for key, _ in oldest:
            _cache.pop(key, None)


def empty_transcript(url: str, *, error: str = "", code: str = "") -> dict[str, Any]:
    return {
        "url": url,
        "language": "",
        "automatic": False,
        "lines": [],
        "text": "",
        "error": error,
        "code": code,
    }


def fetch_transcript(url: str) -> dict[str, Any]:
    cleaned = canonicalize_media_url(validate_url(url))
    cached = _cache_get(cleaned)
    if cached is not None:
        return cached
    opts = base_ydl_opts(use_impersonate=True, use_cookies=False)
    opts.update(
        {
            "skip_download": True,
            "writesubtitles": False,
            "writeautomaticsub": False,
            "noplaylist": True,
        }
    )
    try:
        with YoutubeDL(opts) as ydl:
            info = ydl.extract_info(cleaned, download=False) or {}
    except Exception as exc:
        logger.info("transcript extract failed: %s", exc)
        return empty_transcript(cleaned, error="영상을 읽지 못했습니다. 잠시 후 다시 시도해 주세요.", code="NETWORK_ERROR")
    if not isinstance(info, dict):
        return empty_transcript(cleaned, error="대본을 읽지 못했습니다.", code="EXTRACT_FAILED")
    picked = pick_caption_track(info)
    if picked is None:
        result = empty_transcript(cleaned, error="이 영상은 대본이 없습니다.", code="")
        _cache_put(cleaned, result)
        return result
    language, automatic, track = picked
    raw = str(track.get("data") or "")
    if not raw and track.get("url"):
        try:
            raw = _fetch_caption_text(str(track["url"]))
        except Exception as exc:
            logger.info("transcript download failed: %s", exc)
            return empty_transcript(cleaned, error="대본을 받지 못했습니다. 잠시 후 다시 시도해 주세요.", code="NETWORK_ERROR")
    lines = _parse_caption_body(raw, str(track.get("ext") or ""))
    result = {
        "url": cleaned,
        "language": language,
        "automatic": automatic,
        "lines": lines,
        "text": "\n".join(item["text"] for item in lines),
    }
    _cache_put(cleaned, result)
    return result
