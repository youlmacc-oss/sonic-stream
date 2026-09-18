from __future__ import annotations

import json
import logging
import os
import random
import re
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlparse

from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadCancelled

from app.classify import classify_error
from app.diagnostics import diagnostic_record, mask_text
from app.errors import MESSAGES
from app.local_runtime import evaluate_saved_media, is_local, promote_local_file, runtime_location
from app.quality import describe_resolution, orientation_of, select_download_format, video_format_selector
from app.gc import delete_job_dir, job_dir_for
from app.jobs import store
from app.models import InspectResponse, MediaQuality, MediaType
from app.policy import decide_next
from app.pot import apply_pot, pot_ready
from app.routes import available_routes, configured_routes, cool_route, next_route, recover_route
from app.runtime import ejs_package_present, enabled_js_runtimes
from app.eventlog import emit_event
from app.youtube_auth import apply_youtube_auth, cookie_state, has_cookies

logger = logging.getLogger("sonicstream.ytdlp")

URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SKIP_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".part", ".ytdl", ".json", ".srt", ".vtt"}
MEDIA_EXTS = {".mp4", ".mp3", ".flac", ".m4a", ".webm", ".mkv", ".mov"}
YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?.*?v=|embed/|shorts/|live/|music/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)

# Verified against yt-dlp 2026.08.30 INNERTUBE_CLIENTS. Do not add retired names.
KNOWN_CLIENTS = {
    "android",
    "android_vr",
    "ios",
    "mweb",
    "tv",
    "tv_downgraded",
    "tv_simply",
    "visionos",
    "web",
    "web_creator",
    "web_embedded",
    "web_music",
    "web_safari",
}


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def _cookie_mode() -> str:
    return (os.getenv("YOUTUBE_COOKIE_MODE") or "anonymous_first").strip().lower()


def canonicalize_media_url(url: str) -> str:
    match = YOUTUBE_ID_RE.search(url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return url


def _youtube_id_from_url(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower()
    if host.endswith("youtu.be"):
        return parsed.path.strip("/").split("/")[0] or None
    if "youtube.com" not in host:
        return None
    query_id = (parse_qs(parsed.query).get("v") or [""])[0]
    if query_id:
        return query_id
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 2 and parts[0].lower() in {"shorts", "embed", "live", "v"}:
        return parts[1]
    return None


def validate_url(url: str) -> str:
    cleaned = url.strip()
    if not URL_RE.match(cleaned):
        raise ValueError("INVALID_URL")
    video_id = _youtube_id_from_url(cleaned)
    if video_id is not None and not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
        raise ValueError("INVALID_URL")
    return cleaned


def info_has_audio(info: dict[str, Any]) -> bool | None:
    formats = info.get("formats")
    if not isinstance(formats, list) or not formats:
        acodec = str(info.get("acodec") or "")
        if acodec and acodec != "none":
            return True
        return None
    for item in formats:
        if not isinstance(item, dict):
            continue
        acodec = str(item.get("acodec") or "")
        if acodec and acodec != "none":
            return True
    return False


def validate_combo(media_type: MediaType, quality: MediaQuality) -> None:
    video_ok = media_type == "video" and quality in {"best", "720p", "1080p", "4k"}
    audio_ok = media_type == "audio" and quality in {"320k", "flac"}
    if not (video_ok or audio_ok):
        raise ValueError("PROCESS_FAILED")


def download_client_attempts(*, use_cookies: bool, pot_ok: bool) -> list[list[str] | None]:
    attempts: list[list[str] | None] = [None]
    if pot_ok:
        attempts.append(["mweb"])
        attempts.append(["web_safari"])
        attempts.append(["android_vr"])
    else:
        # No-POT clients first after default. Datacenter IPs often fail default with BOT_CHECK.
        attempts.append(["tv"])
        attempts.append(["android"])
        attempts.append(["mweb"])
        attempts.append(["web_safari"])
        attempts.append(["android_vr"])
        attempts.append(["web_embedded"])
    if use_cookies:
        attempts.append(["web"])
    unique: list[list[str] | None] = []
    seen: set[tuple[str, ...]] = set()
    for item in attempts:
        key = tuple(item) if item else ("__default__",)
        if key in seen:
            continue
        if item and any(client not in KNOWN_CLIENTS for client in item):
            continue
        seen.add(key)
        unique.append(item)
    return unique


def inspect_client_attempts() -> list[list[str] | None]:
    return [None, ["web_safari"], ["android_vr"]]


class JobYDLLogger:
    def __init__(
        self,
        job_id: str,
        attempt_number: int | None = None,
        request_id: str | None = None,
        stage: str = "extract",
    ) -> None:
        self.job_id = job_id
        self.attempt_number = attempt_number
        self.request_id = request_id
        self.stage = stage

    def set_stage(self, stage: str) -> None:
        self.stage = stage

    def debug(self, msg: object) -> None:
        self._emit(str(msg), "debug")

    def info(self, msg: object) -> None:
        self._emit(str(msg), "info")

    def warning(self, msg: object) -> None:
        self._emit(str(msg), "warning", force=True)

    def error(self, msg: object) -> None:
        self._emit(str(msg), "error", force=True)

    def _emit(self, text: str, level: str, *, force: bool = False) -> None:
        lowered = text.lower()
        interesting = any(
            token in lowered
            for token in ("po token", "potoken", "js challenge", "javascript", "player_client", "format")
        )
        if not force and not interesting:
            return
        emit_event(
            event="warning",
            stage=self.stage,
            request_id=self.request_id,
            job_id=self.job_id,
            attempt_number=self.attempt_number,
            error_message=text,
            origin="external",
            extra={"log_level": level},
        )


def apply_ip_mode(opts: dict[str, Any]) -> dict[str, Any]:
    mode = (os.getenv("YOUTUBE_IP_MODE") or "").strip().lower()
    if mode == "ipv4":
        opts["source_address"] = "0.0.0.0"
    elif mode == "ipv6":
        opts["source_address"] = "::"
    return opts


def base_ydl_opts(
    *,
    player_clients: list[str] | None = None,
    use_impersonate: bool = True,
    proxy: str | None = None,
    use_cookies: bool = False,
    **extra: Any,
) -> dict[str, Any]:
    extra.pop("player_clients", None)
    extra.pop("use_impersonate", None)
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": False,
        "noplaylist": True,
        "socket_timeout": 25,
        "retries": 1,
        "fragment_retries": 1,
        "extractor_retries": 1,
        "geo_bypass": True,
    }
    runtimes = enabled_js_runtimes()
    if runtimes:
        opts["js_runtimes"] = runtimes
    if not ejs_package_present():
        opts["remote_components"] = ["ejs:github"]
    if player_clients:
        youtube_args = opts.setdefault("extractor_args", {}).setdefault("youtube", {})
        youtube_args["player_client"] = list(player_clients)
    apply_ip_mode(opts)
    if pot_ready():
        apply_pot(opts)
    apply_youtube_auth(opts, proxy=proxy, use_cookies=use_cookies, use_impersonate=use_impersonate)
    opts.update(extra)
    return opts


def _korean_view_count(count: int) -> str:
    if count >= 100_000_000:
        value = count / 100_000_000
        return f"{value:.1f}".rstrip("0").rstrip(".") + "억회"
    if count >= 10_000:
        value = count / 10_000
        text = f"{int(value)}만회" if value >= 100 else f"{value:.1f}".rstrip("0").rstrip(".") + "만회"
        return text
    if count >= 1_000:
        value = count / 1_000
        return f"{value:.1f}".rstrip("0").rstrip(".") + "천회"
    return f"{count}회"


def format_view_count(value: object) -> str:
    if value in (None, "", 0, "0"):
        return ""
    if isinstance(value, str):
        text = " ".join(value.split())
        if re.search(r"조회수\s*없음|no views|hidden", text, re.I):
            return ""
        compact = text.replace(" ", "")
        labeled = re.search(r"([\d.,]+[만천억]회)", compact)
        if labeled:
            return labeled.group(1)
        english = re.search(r"([\d.,]+)\s*([KMB])\s*views?", text, re.I)
        if english:
            amount = float(english.group(1).replace(",", ""))
            factor = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}[english.group(2).upper()]
            return _korean_view_count(int(amount * factor))
        digits = re.sub(r"[^\d]", "", text)
        if not digits:
            return ""
        return _korean_view_count(int(digits))
    try:
        count = int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return ""
    if count <= 0:
        return ""
    return _korean_view_count(count)


def format_duration(seconds: object) -> str:
    if seconds is None:
        return "00:00"
    try:
        total = int(float(seconds))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "00:00"
    if total < 0:
        return "00:00"
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def pick_thumbnail(info: dict[str, Any]) -> str:
    thumbs = info.get("thumbnails") or []
    if thumbs:
        def score(thumb: dict[str, Any]) -> int:
            url = str(thumb.get("url") or "")
            width = int(thumb.get("width") or 0)
            bonus = 100_000 if "maxres" in url else 0
            return width + bonus

        best = max(thumbs, key=score)
        return str(best.get("url") or info.get("thumbnail") or "")
    return str(info.get("thumbnail") or "")


def pick_author(info: dict[str, Any]) -> str:
    for key in ("artist", "uploader", "channel", "creator", "uploader_id"):
        value = info.get(key)
        if value:
            return str(value)
    return "Unknown"


def is_live(info: dict[str, Any]) -> bool:
    if info.get("is_live"):
        return True
    return info.get("live_status") in {"is_live", "is_upcoming"}


def metadata_thin(info: dict[str, Any] | None) -> bool:
    if not info:
        return True
    has_title = bool(info.get("title"))
    has_thumb = bool(info.get("thumbnail") or info.get("thumbnails"))
    has_duration = info.get("duration") is not None
    return not (has_title and has_thumb and has_duration)


def inspect_via_ytdlp(url: str, clients: list[str] | None) -> dict[str, Any]:
    use_cookies = _cookie_mode() == "always" and has_cookies()
    opts = base_ydl_opts(skip_download=True, player_clients=clients, use_cookies=use_cookies)
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


def inspect_via_oembed(url: str) -> tuple[InspectResponse | None, bool]:
    endpoints = (
        f"https://www.youtube.com/oembed?format=json&url={quote(url, safe='')}",
        f"https://noembed.com/embed?url={quote(url, safe='')}",
    )
    request_headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    saw_404 = False
    for endpoint in endpoints:
        try:
            request = urllib.request.Request(endpoint, headers=request_headers)
            with urllib.request.urlopen(request, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                saw_404 = True
            continue
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict):
            continue
        title = str(data.get("title") or "").strip()
        if not title:
            continue
        return InspectResponse(
            title=title,
            author=str(data.get("author_name") or data.get("author") or "Unknown"),
            duration="",
            thumbnail=str(data.get("thumbnail_url") or ""),
            preview_only=True,
            duration_known=False,
            webpage_url=url,
        ), False
    return None, saw_404


def inspect_to_response(info: dict[str, Any]) -> InspectResponse:
    if is_live(info):
        raise RuntimeError(f"LIVE_STREAM|{MESSAGES['LIVE_STREAM']}")
    title = str(info.get("title") or info.get("fulltitle") or "").strip()
    if not title:
        raise RuntimeError(f"EXTRACT_FAILED|{MESSAGES['EXTRACT_FAILED']}")
    try:
        width = int(info.get("width") or 0) or None
    except (TypeError, ValueError):
        width = None
    try:
        height = int(info.get("height") or 0) or None
    except (TypeError, ValueError):
        height = None
    duration_raw = info.get("duration")
    return InspectResponse(
        title=title,
        author=pick_author(info),
        duration=format_duration(duration_raw) if duration_raw is not None else "",
        thumbnail=pick_thumbnail(info),
        preview_only=False,
        duration_known=duration_raw is not None,
        width=width,
        height=height,
        aspect_ratio=describe_resolution(width, height),
        orientation=orientation_of(width, height),
        webpage_url=str(info.get("webpage_url") or "") or None,
    )


def normalize_search_query(raw: str) -> str:
    text = " ".join((raw or "").split())
    if not text or len(text) > 80:
        raise ValueError("INVALID_URL")
    if "\x00" in text:
        raise ValueError("INVALID_URL")
    return text


YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
# Same filter youtube.com uses for results?sp=EgIQAQ%3D%3D (동영상 only).
YOUTUBE_SEARCH_VIDEO_PARAMS = "EgIQAQ=="
_SEARCH_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_SEARCH_CACHE_LOCK = threading.Lock()
_SEARCH_CACHE_TTL_SEC = 90.0
_SEARCH_CACHE_MAX = 32


def _search_cache_key(query: str, limit: int) -> str:
    return f"{limit}:{query}"


def _search_cache_get(query: str, limit: int) -> dict[str, Any] | None:
    key = _search_cache_key(query, limit)
    with _SEARCH_CACHE_LOCK:
        item = _SEARCH_CACHE.get(key)
        if item is None:
            return None
        stamped, payload = item
        if time.monotonic() - stamped > _SEARCH_CACHE_TTL_SEC:
            _SEARCH_CACHE.pop(key, None)
            return None
        return {"query": payload["query"], "items": list(payload["items"])}


def _search_cache_put(query: str, limit: int, payload: dict[str, Any]) -> None:
    key = _search_cache_key(query, limit)
    with _SEARCH_CACHE_LOCK:
        _SEARCH_CACHE[key] = (time.monotonic(), {"query": payload["query"], "items": list(payload["items"])})
        if len(_SEARCH_CACHE) > _SEARCH_CACHE_MAX:
            oldest = min(_SEARCH_CACHE, key=lambda name: _SEARCH_CACHE[name][0])
            _SEARCH_CACHE.pop(oldest, None)


def _innertube_text(value: object) -> str:
    if isinstance(value, str):
        return value.strip()
    if not isinstance(value, dict):
        return ""
    simple = value.get("simpleText") or value.get("content")
    if simple:
        return str(simple).strip()
    runs = value.get("runs")
    if isinstance(runs, list):
        return "".join(str(part.get("text") or "") for part in runs if isinstance(part, dict)).strip()
    return ""


def _is_watch_id(value: object) -> bool:
    return bool(YOUTUBE_VIDEO_ID_RE.fullmatch(str(value or "").strip()))


def _thumb_and_duration(node: object) -> tuple[str, str]:
    thumb = ""
    duration = ""

    def walk(obj: object) -> None:
        nonlocal thumb, duration
        if isinstance(obj, dict):
            url = obj.get("url")
            if not thumb and isinstance(url, str) and "ytimg.com" in url:
                thumb = url
            badge = obj.get("thumbnailBadgeViewModel")
            if not duration and isinstance(badge, dict):
                duration = _innertube_text(badge.get("text"))
            for child in obj.values():
                walk(child)
        elif isinstance(obj, list):
            for child in obj:
                walk(child)

    walk(node)
    return thumb, duration


def _hit_from_parts(
    video_id: str,
    title: str,
    author: str,
    thumbnail: str,
    duration: str,
    views: str = "",
) -> dict[str, Any] | None:
    if not _is_watch_id(video_id):
        return None
    return {
        "title": (title or "").strip() or video_id,
        "author": (author or "").strip() or "Unknown",
        "url": f"https://www.youtube.com/watch?v={video_id}",
        "thumbnail": thumbnail or f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
        "duration": duration,
        "duration_known": bool(duration),
        "views": views,
    }


def search_hits_from_innertube(payload: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    seen: set[str] = set()

    def add(hit: dict[str, Any] | None) -> None:
        if hit is None or hit["url"] in seen:
            return
        seen.add(hit["url"])
        items.append(hit)

    def from_video_renderer(renderer: dict[str, Any]) -> None:
        thumbs = renderer.get("thumbnail")
        thumb_url = ""
        if isinstance(thumbs, dict):
            sources = thumbs.get("thumbnails")
            if isinstance(sources, list) and sources and isinstance(sources[-1], dict):
                thumb_url = str(sources[-1].get("url") or "")
        author = (
            _innertube_text(renderer.get("ownerText"))
            or _innertube_text(renderer.get("longBylineText"))
            or _innertube_text(renderer.get("shortBylineText"))
        )
        add(
            _hit_from_parts(
                str(renderer.get("videoId") or ""),
                _innertube_text(renderer.get("title")),
                author,
                thumb_url,
                _innertube_text(renderer.get("lengthText")),
                format_view_count(
                    _innertube_text(renderer.get("shortViewCountText"))
                    or _innertube_text(renderer.get("viewCountText"))
                ),
            )
        )

    def from_lockup(model: dict[str, Any]) -> None:
        meta = model.get("metadata") if isinstance(model.get("metadata"), dict) else {}
        lockup = meta.get("lockupMetadataViewModel") if isinstance(meta, dict) else {}
        title = ""
        author = ""
        views = ""
        if isinstance(lockup, dict):
            title = _innertube_text(lockup.get("title"))
            rows_wrap = lockup.get("metadata") if isinstance(lockup.get("metadata"), dict) else {}
            rows_model = rows_wrap.get("contentMetadataViewModel") if isinstance(rows_wrap, dict) else {}
            parts: list[str] = []
            for row in (rows_model or {}).get("metadataRows") or []:
                if not isinstance(row, dict):
                    continue
                for part in row.get("metadataParts") or []:
                    if not isinstance(part, dict):
                        continue
                    text = _innertube_text(part.get("text"))
                    if text:
                        parts.append(text)
            author = parts[0] if parts else ""
            for text in parts[1:]:
                maybe = format_view_count(text)
                if maybe:
                    views = maybe
                    break
        thumb, duration = _thumb_and_duration(model.get("contentImage"))
        add(_hit_from_parts(str(model.get("contentId") or ""), title, author, thumb, duration, views))

    def walk(obj: object) -> None:
        if isinstance(obj, dict):
            renderer = obj.get("videoRenderer")
            if isinstance(renderer, dict):
                from_video_renderer(renderer)
                return
            lockup = obj.get("lockupViewModel")
            if isinstance(lockup, dict):
                from_lockup(lockup)
                return
            reel = obj.get("reelItemRenderer")
            if isinstance(reel, dict):
                add(
                    _hit_from_parts(
                        str(reel.get("videoId") or ""),
                        _innertube_text(reel.get("headline")),
                        "",
                        "",
                        "",
                    )
                )
                return
            for child in obj.values():
                walk(child)
        elif isinstance(obj, list):
            for child in obj:
                walk(child)

    walk(payload)
    return items


SEARCH_RESULT_MAX = 30
YTDLP_SEARCH_MAX = 20
YTSEARCH_LIMIT = 12


def _innertube_context() -> dict[str, Any]:
    try:
        from yt_dlp.extractor.youtube._base import INNERTUBE_CLIENTS
    except Exception:
        INNERTUBE_CLIENTS = {}
    meta = INNERTUBE_CLIENTS.get("web") if isinstance(INNERTUBE_CLIENTS, dict) else None
    ctx = json.loads(json.dumps((meta or {}).get("INNERTUBE_CONTEXT") or {"client": {}}))
    client = ctx.setdefault("client", {})
    client["clientName"] = "WEB"
    client["hl"] = "ko"
    client["gl"] = "KR"
    client.setdefault("clientVersion", "2.20260708.00.00")
    return ctx


def _innertube_post(body: dict[str, Any], query: str) -> dict[str, Any]:
    ctx = body.get("context") if isinstance(body.get("context"), dict) else {}
    client = ctx.get("client") if isinstance(ctx.get("client"), dict) else {}
    request = urllib.request.Request(
        "https://www.youtube.com/youtubei/v1/search?prettyPrint=false",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
            ),
            "Origin": "https://www.youtube.com",
            "Referer": f"https://www.youtube.com/results?search_query={quote(query)}",
            "X-YouTube-Client-Name": "1",
            "X-YouTube-Client-Version": str(client.get("clientVersion") or "2.20260708.00.00"),
        },
    )
    with urllib.request.urlopen(request, timeout=8) as response:
        payload = json.loads(response.read().decode("utf-8", "replace"))
    return payload if isinstance(payload, dict) else {}


def innertube_continuation_token(payload: dict[str, Any]) -> str | None:
    found: list[str] = []

    def walk(obj: object) -> None:
        if found:
            return
        if isinstance(obj, dict):
            command = obj.get("continuationCommand")
            if isinstance(command, dict):
                token = str(command.get("token") or "").strip()
                if token:
                    found.append(token)
                    return
            for child in obj.values():
                walk(child)
        elif isinstance(obj, list):
            for child in obj:
                walk(child)

    walk(payload)
    return found[0] if found else None


def _merge_search_hits(items: list[dict[str, Any]], extra: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    seen = {str(item.get("url") or "") for item in items}
    for hit in extra:
        url = str(hit.get("url") or "")
        if not url or url in seen:
            continue
        items.append(hit)
        seen.add(url)
        if len(items) >= limit:
            break
    return items[:limit]


def search_via_innertube(query: str, limit: int) -> list[dict[str, Any]]:
    ctx = _innertube_context()
    payload = _innertube_post(
        {"context": ctx, "query": query, "params": YOUTUBE_SEARCH_VIDEO_PARAMS},
        query,
    )
    items = search_hits_from_innertube(payload)
    if len(items) >= limit:
        return items[:limit]
    token = innertube_continuation_token(payload)
    if not token:
        return items[:limit]
    try:
        more = _innertube_post({"context": ctx, "continuation": token}, query)
        items = _merge_search_hits(items, search_hits_from_innertube(more), limit)
    except Exception as exc:
        logger.info("Innertube continuation skipped: %s", exc)
    return items[:limit]


def search_ytsearch(query: str, limit: int = YTSEARCH_LIMIT) -> list[dict[str, Any]]:
    cleaned = normalize_search_query(query)
    count = max(1, min(int(limit or YTSEARCH_LIMIT), YTSEARCH_LIMIT))
    opts = base_ydl_opts(use_impersonate=True, use_cookies=False)
    opts.update(
        {
            "skip_download": True,
            "extract_flat": "in_playlist",
            "noplaylist": False,
            "playlistend": count,
            "geo_bypass_country": "KR",
        }
    )
    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(f"ytsearch{count}:{cleaned}", download=False) or {}
    return search_hits_from_info(info)[:count]


def search_via_ytdlp(query: str, limit: int) -> list[dict[str, Any]]:
    opts = base_ydl_opts(use_impersonate=True, use_cookies=False)
    opts.update(
        {
            "skip_download": True,
            "extract_flat": "in_playlist",
            "noplaylist": False,
            "playlistend": limit,
            "geo_bypass_country": "KR",
        }
    )
    last_error: Exception | None = None
    for target in (
        f"ytsearch{limit}:{query}",
        f"https://www.youtube.com/results?search_query={quote(query)}",
    ):
        try:
            with YoutubeDL(opts) as ydl:
                info = ydl.extract_info(target, download=False) or {}
            hits = search_hits_from_info(info)
            if hits:
                return hits[:limit]
        except Exception as exc:
            last_error = exc
            logger.info("yt-dlp search miss via %s: %s", target[:48], exc)
    if last_error is not None:
        logger.info("yt-dlp search exhausted: %s", last_error)
    return []


def search_hits_from_info(info: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for entry in info.get("entries") or []:
        if not isinstance(entry, dict):
            continue
        video_id = str(entry.get("id") or "").strip()
        url = str(entry.get("webpage_url") or entry.get("url") or "").strip()
        if video_id and len(video_id) == 11:
            url = f"https://www.youtube.com/watch?v={video_id}"
        elif url.startswith("http") and YOUTUBE_ID_RE.search(url):
            url = canonicalize_media_url(url)
        if not url.startswith("http"):
            continue
        duration_raw = entry.get("duration")
        duration_known = duration_raw not in (None, "", 0, "0")
        items.append(
            {
                "title": str(entry.get("title") or url),
                "author": pick_author(entry),
                "url": url,
                "thumbnail": pick_thumbnail(entry) or (f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg" if video_id else ""),
                "duration": format_duration(duration_raw) if duration_known else "",
                "duration_known": bool(duration_known),
                "views": format_view_count(entry.get("view_count") or entry.get("views")),
            }
        )
    return items


def search_videos(query: str, limit: int = 30) -> dict[str, Any]:
    cleaned = normalize_search_query(query)
    count = max(1, min(int(limit or 30), SEARCH_RESULT_MAX))
    cached = _search_cache_get(cleaned, count)
    if cached is not None:
        return cached
    items: list[dict[str, Any]] = []
    try:
        items = search_via_innertube(cleaned, count)
    except Exception as exc:
        logger.info("Innertube search failed: %s", exc)
    if len(items) < 3:
        fallback = search_via_ytdlp(cleaned, min(count, YTDLP_SEARCH_MAX))
        if fallback:
            items = fallback
    result = {"query": cleaned, "items": items[:count]}
    if items:
        _search_cache_put(cleaned, count, result)
    return result


def inspect_url(url: str) -> InspectResponse:
    cleaned = canonicalize_media_url(validate_url(url))
    last_error: Exception | None = None
    is_youtube = YOUTUBE_ID_RE.search(cleaned) is not None
    oembed_preview: InspectResponse | None = None
    oembed_404 = False

    if is_youtube:
        oembed_preview, oembed_404 = inspect_via_oembed(cleaned)
        if oembed_preview is not None:
            return oembed_preview

    for clients in inspect_client_attempts():
        try:
            info = inspect_via_ytdlp(cleaned, clients)
            if metadata_thin(info):
                continue
            return inspect_to_response(info)
        except Exception as exc:
            last_error = exc
            label = ",".join(clients) if clients else "default"
            logger.warning("yt-dlp inspect failed (%s): %s", label, mask_text(str(exc)))

    if oembed_preview is None and not is_youtube:
        oembed_preview, extra_404 = inspect_via_oembed(cleaned)
        oembed_404 = oembed_404 or extra_404
        if oembed_preview is not None:
            return oembed_preview

    if last_error is not None:
        classified = classify_error(last_error)
        raise RuntimeError(f"{classified.code}|{classified.user_message}") from last_error
    if oembed_404:
        raise RuntimeError(f"EXTRACT_FAILED|{MESSAGES['EXTRACT_FAILED']}")
    raise RuntimeError(f"EXTRACT_FAILED|{MESSAGES['EXTRACT_FAILED']}")


def format_speed(bytes_per_sec: object) -> str:
    try:
        speed = float(bytes_per_sec)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return "0 KB/s"
    if speed <= 0:
        return "0 KB/s"
    if speed >= 1024 * 1024:
        return f"{speed / (1024 * 1024):.1f} MB/s"
    return f"{speed / 1024:.1f} KB/s"


def make_progress_hook(job_id: str):
    def hook(payload: dict[str, Any]) -> None:
        job = store.get(job_id)
        if job is not None and job.cancel_event.is_set():
            raise DownloadCancelled("job cancelled")
        status = payload.get("status")
        if status == "downloading":
            total = payload.get("total_bytes") or payload.get("total_bytes_estimate") or 0
            downloaded = payload.get("downloaded_bytes") or 0
            percent = 0.0
            detail = "영상 정보 확인 중..."
            if total:
                percent = min(100.0, downloaded / total * 100.0)
                detail = ""
            elif downloaded:
                detail = "받는 중 (전체 크기 미확인)"
            eta_raw = payload.get("eta")
            eta = int(eta_raw) if isinstance(eta_raw, (int, float)) else None
            store.update(
                job_id,
                status="downloading",
                percent=round(percent, 1),
                speed=format_speed(payload.get("speed")),
                eta=eta,
                detail=detail,
            )
        elif status == "finished":
            job = store.get(job_id)
            store.update(
                job_id,
                status="processing",
                percent=95.0,
                detail=job.processing_copy() if job else "FFmpeg 패키징 및 태그 주입 중...",
            )

    return hook


def build_ydl_opts(
    job_id: str,
    media_type: MediaType,
    quality: MediaQuality,
    job_dir: Path,
    player_clients: list[str] | None = None,
    proxy: str | None = None,
    use_cookies: bool = False,
    use_impersonate: bool = True,
    attempt_number: int | None = None,
    request_id: str | None = None,
) -> dict[str, Any]:
    outtmpl = str(job_dir / "%(title)s.%(ext)s")
    opts = base_ydl_opts(
        player_clients=player_clients,
        proxy=proxy,
        use_cookies=use_cookies,
        use_impersonate=use_impersonate,
        windowsfilenames=True,
        progress_hooks=[make_progress_hook(job_id)],
        outtmpl=outtmpl,
        logger=JobYDLLogger(job_id, attempt_number, request_id),
    )
    ffmpeg_dir = resolve_ffmpeg_dir()
    if ffmpeg_dir is not None:
        opts["ffmpeg_location"] = str(ffmpeg_dir)

    if media_type == "video":
        opts.update(
            {
                "format": video_format_selector(quality),
                "merge_output_format": "mp4",
                "postprocessors": [{"key": "FFmpegMetadata"}],
                "postprocessor_args": {
                    "ffmpeg": ["-movflags", "+faststart"],
                    "merger": ["-movflags", "+faststart"],
                },
            }
        )
        return opts

    codec = "mp3" if quality == "320k" else "flac"
    extract: dict[str, Any] = {
        "key": "FFmpegExtractAudio",
        "preferredcodec": codec,
    }
    if quality == "320k":
        extract["preferredquality"] = "320"

    opts.update(
        {
            "format": "bestaudio/best",
            "writethumbnail": True,
            "postprocessors": [
                {"key": "FFmpegThumbnailsConvertor", "format": "jpg", "when": "before_dl"},
                extract,
                {"key": "FFmpegMetadata"},
                {"key": "EmbedThumbnail"},
            ],
        }
    )
    return opts


def find_media_file(job_dir: Path) -> Path | None:
    if not job_dir.exists():
        return None
    files = [
        path
        for path in job_dir.iterdir()
        if path.is_file() and path.suffix.lower() not in SKIP_EXTS
    ]
    preferred = [path for path in files if path.suffix.lower() in {".mp4", ".mp3", ".flac"}]
    candidates = preferred or [path for path in files if path.suffix.lower() in MEDIA_EXTS]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def sanitize_filename(name: str) -> str:
    cleaned = UNSAFE_FILENAME.sub("", name).strip(" .")
    if not cleaned:
        cleaned = "sonicstream"
    if len(cleaned) > 180:
        stem, suffix = Path(cleaned).stem, Path(cleaned).suffix
        cleaned = f"{stem[: 180 - len(suffix)]}{suffix}"
    return cleaned


def ascii_fallback(name: str) -> str:
    encoded = name.encode("ascii", "ignore").decode("ascii").strip() or "download"
    return UNSAFE_FILENAME.sub("", encoded) or "download"


def content_disposition(filename: str) -> str:
    safe = sanitize_filename(filename)
    fallback = ascii_fallback(safe)
    return f"attachment; filename=\"{fallback}\"; filename*=UTF-8''{quote(safe)}"


def media_type_for(path: Path) -> str:
    return {
        ".mp4": "video/mp4",
        ".mp3": "audio/mpeg",
        ".flac": "audio/flac",
        ".m4a": "audio/mp4",
        ".webm": "video/webm",
        ".mkv": "video/x-matroska",
    }.get(path.suffix.lower(), "application/octet-stream")


_FFMPEG_DIR: Path | None | bool = False


def reset_ffmpeg_dir_cache() -> None:
    global _FFMPEG_DIR
    _FFMPEG_DIR = False


def _ffmpeg_from_env() -> Path | None:
    raw = (os.getenv("SONICSTREAM_FFMPEG_DIR") or os.getenv("FFMPEG_LOCATION") or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if path.is_file() and path.name.lower().startswith("ffmpeg"):
        return path.resolve().parent
    binary = path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    if binary.is_file():
        return path.resolve()
    return None


def resolve_ffmpeg_dir() -> Path | None:
    global _FFMPEG_DIR
    env_dir = _ffmpeg_from_env()
    if env_dir is not None:
        return env_dir
    if _FFMPEG_DIR is not False:
        return _FFMPEG_DIR  # type: ignore[return-value]

    which = shutil.which("ffmpeg")
    if which:
        _FFMPEG_DIR = Path(which).resolve().parent
        return _FFMPEG_DIR

    extra_roots = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        Path(os.environ.get("ProgramFiles", "")) / "ffmpeg",
        Path(r"C:\ffmpeg"),
    ]
    for root in extra_roots:
        try:
            if not root.exists():
                continue
            match = next(root.glob("Gyan.FFmpeg*/**/bin/ffmpeg.exe"), None)
            if match is None:
                match = next(root.rglob("ffmpeg.exe"), None)
        except OSError:
            match = None
        if match:
            _FFMPEG_DIR = match.parent
            return _FFMPEG_DIR

    _FFMPEG_DIR = None
    return None


def ffmpeg_available() -> bool:
    ffmpeg_dir = resolve_ffmpeg_dir()
    if ffmpeg_dir is None:
        return False
    binary = ffmpeg_dir / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    try:
        completed = subprocess.run(
            [str(binary), "-version"],
            capture_output=True,
            check=False,
            timeout=5,
        )
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def interruptible_sleep(job_id: str, seconds: float) -> None:
    end = time.time() + max(0.0, seconds)
    while time.time() < end:
        job = store.get(job_id)
        if job is None or job.cancel_event.is_set() or job.settled:
            raise DownloadCancelled("job cancelled")
        time.sleep(min(0.25, end - time.time()))


def _job_ids(job_id: str) -> tuple[str | None, str | None]:
    job = store.get(job_id)
    return (job.request_id if job else None, job.snapshot_id if job else None)


def _fail_job(job_id: str, url: str, media_type: str, quality: str, exc: BaseException, code: str, message: str) -> None:
    logger.warning("Job %s failed (%s): %s", job_id, code, mask_text(str(exc)))
    request_id, _snapshot = _job_ids(job_id)
    emit_event(
        event="failed",
        stage="download",
        request_id=request_id,
        job_id=job_id,
        error_code=code,
        error_message=str(exc),
        user_message=message,
        exc=exc,
        url=url,
        media_type=media_type,
        quality=quality,
        origin="external" if code not in {"PROCESS_FAILED", "UNKNOWN"} else "internal",
        extra={"final": True},
    )
    store.settle(job_id, "error", error_code=code, error_message=message)
    delete_job_dir(job_id)


def run_download(job_id: str, url: str, media_type: MediaType, quality: MediaQuality) -> None:
    job_dir = job_dir_for(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    store.mark_worker(job_id, True)
    store.update(job_id, status="downloading", percent=0.0, speed="0 KB/s")
    request_id, _snapshot = _job_ids(job_id)
    emit_event(
        event="started",
        stage="download",
        request_id=request_id,
        job_id=job_id,
        media_type=media_type,
        quality=quality,
        url=url,
        origin="internal",
    )

    try:
        cleaned = canonicalize_media_url(validate_url(url))
        cookie_mode = _cookie_mode()
        use_cookies = cookie_mode == "always" and has_cookies()
        pot_ok = pot_ready()
        clients = download_client_attempts(use_cookies=use_cookies or has_cookies(), pot_ok=pot_ok)
        client_index = 0
        configured = configured_routes()
        if not configured:
            _fail_job(job_id, url, media_type, quality, RuntimeError("ROUTE_CONFIG"), "ROUTE_CONFIG", MESSAGES["ROUTE_CONFIG"])
            return
        routes = available_routes()
        if not routes:
            _fail_job(job_id, url, media_type, quality, RuntimeError("ROUTE_COOL"), "ROUTE_COOL", MESSAGES["ROUTE_COOL"])
            return
        route = routes[0]
        attempts = 0
        waits_used = 0
        route_switches = 0
        use_impersonate = True
        impersonate_reset = False
        max_attempts = _int_env("MAX_JOB_ATTEMPTS", 10)
        max_waits = _int_env("MAX_RATE_LIMIT_WAITS", 2)
        max_route_switches = _int_env("MAX_ROUTE_SWITCHES", 1)
        deadline = time.time() + _int_env("JOB_TIMEOUT_SECONDS", 720)
        last_error: BaseException | None = None
        last_code = "UNKNOWN"
        last_message = MESSAGES["UNKNOWN"]

        while attempts < max_attempts:
            job = store.get(job_id)
            if job is None or job.settled:
                return
            if job.cancel_event.is_set() or time.time() > deadline:
                raise TimeoutError("TIMEOUT")

            attempts += 1
            clients_now = clients[client_index] if client_index < len(clients) else None
            attempt_dir = job_dir / f"attempt_{attempts}"
            attempt_dir.mkdir(parents=True, exist_ok=True)
            stage = "extract"
            started = time.time()
            store.update(
                job_id,
                status="downloading",
                attempt=attempts,
                route_alias=route.alias,
                wait_reason=None,
                detail="",
            )
            emit_event(
                event="started",
                stage="extract",
                request_id=request_id,
                job_id=job_id,
                attempt_number=attempts,
                strategy="default" if clients_now is None else "player_client",
                client=",".join(clients_now) if clients_now else "default",
                route_alias=route.alias,
                media_type=media_type,
                quality=quality,
                url=cleaned,
                origin="internal",
            )

            try:
                opts = build_ydl_opts(
                    job_id,
                    media_type,
                    quality,
                    attempt_dir,
                    player_clients=clients_now,
                    proxy=route.proxy,
                    use_cookies=use_cookies,
                    use_impersonate=use_impersonate,
                    attempt_number=attempts,
                    request_id=request_id,
                )
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(cleaned, download=False) or {}
                    if is_live(info):
                        raise RuntimeError("LIVE_STREAM")
                    if store.get(job_id) and store.get(job_id).cancel_event.is_set():  # type: ignore[union-attr]
                        raise DownloadCancelled("job cancelled")
                    logger_obj = opts.get("logger")
                    if media_type == "video":
                        chosen, spec = select_download_format(
                            list(info.get("formats") or []),
                            quality,
                            rotation=info.get("rotation") or 0,
                        )
                        params = getattr(ydl, "params", None)
                        if isinstance(params, dict):
                            params["format"] = spec
                        if chosen:
                            store.update(
                                job_id,
                                actual_width=int(chosen.get("width") or 0) or None,
                                actual_height=int(chosen.get("height") or 0) or None,
                                actual_quality=describe_resolution(chosen.get("width"), chosen.get("height")),
                                detail="선택한 화질로 받는 중...",
                            )
                    stage = "download"
                    if isinstance(logger_obj, JobYDLLogger):
                        logger_obj.set_stage("download")
                    ydl.process_ie_result(info, download=True)

                stage = "process"
                if isinstance(opts.get("logger"), JobYDLLogger):
                    opts["logger"].set_stage("process")
                output = find_media_file(attempt_dir)
                if output is None:
                    raise RuntimeError("PROCESS_FAILED")

                recover_route(route.alias)
                filename = sanitize_filename(output.name)
                saved_path = None
                file_bytes = output.stat().st_size if output.exists() else None
                verified = False
                delivery = "browser"
                probe: dict = {}
                if is_local():
                    saved = promote_local_file(output, filename, job_id=job_id)
                    saved_path = str(saved)
                    verdict = evaluate_saved_media(
                        saved,
                        media_type,
                        source_has_audio=info_has_audio(info) if isinstance(info, dict) else None,
                        ffmpeg_dir=resolve_ffmpeg_dir(),
                    )
                    probe = verdict.get("probe") or {}
                    file_bytes = verdict.get("file_bytes") or saved.stat().st_size
                    if not verdict.get("ok"):
                        try:
                            saved.unlink()
                        except OSError:
                            pass
                        raise RuntimeError(str(verdict.get("code") or "VERIFY_FAILED"))
                    verified = True
                    delivery = "local_file"
                settled = store.settle(
                    job_id,
                    "done",
                    percent=100.0,
                    file_path=output,
                    filename=filename,
                    download_url=f"/api/fetch/{job_id}",
                    saved_path=saved_path,
                    file_bytes=file_bytes,
                    verified=verified,
                    location=runtime_location(),
                    delivery=delivery,
                    actual_width=probe.get("width") or getattr(store.get(job_id), "actual_width", None),
                    actual_height=probe.get("height") or getattr(store.get(job_id), "actual_height", None),
                    detail="",
                )
                emit_event(
                    event="succeeded",
                    stage="postprocess",
                    request_id=request_id,
                    job_id=job_id,
                    attempt_number=attempts,
                    client=",".join(clients_now) if clients_now else "default",
                    route_alias=route.alias,
                    media_type=media_type,
                    quality=quality,
                    url=cleaned,
                    elapsed_ms=int((time.time() - started) * 1000),
                    origin="internal",
                )
                if settled is None:
                    delete_job_dir(job_id)
                return
            except DownloadCancelled:
                emit_event(
                    event="cancelled",
                    stage=stage,
                    request_id=request_id,
                    job_id=job_id,
                    attempt_number=attempts,
                    error_code="TIMEOUT",
                    error_message=MESSAGES["TIMEOUT"],
                    media_type=media_type,
                    quality=quality,
                    url=cleaned,
                    origin="internal",
                )
                store.settle(job_id, "error", error_code="TIMEOUT", error_message=MESSAGES["TIMEOUT"])
                delete_job_dir(job_id)
                return
            except Exception as exc:
                if str(exc) == "LIVE_STREAM":
                    classified_code, classified_message = "LIVE_STREAM", MESSAGES["LIVE_STREAM"]
                    retry_after = None
                elif str(exc) in {"PROCESS_FAILED", "VERIFY_FAILED", "VERIFY_UNAVAILABLE"}:
                    classified_code = str(exc)
                    classified_message = MESSAGES.get(classified_code, MESSAGES["PROCESS_FAILED"])
                    retry_after = None
                else:
                    classified = classify_error(exc, stage=stage)
                    classified_code, classified_message = classified.code, classified.user_message
                    retry_after = classified.retry_after

                last_error = exc
                last_code = classified_code
                last_message = classified_message
                logger.info(
                    "youtube_attempt %s",
                    diagnostic_record(
                        job_id=job_id,
                        attempt=attempts,
                        stage=stage,
                        route_alias=route.alias,
                        client=",".join(clients_now) if clients_now else "default",
                        elapsed_ms=int((time.time() - started) * 1000),
                        code=classified_code,
                        error_type=type(exc).__name__,
                        error_message=str(exc),
                    ),
                )
                emit_event(
                    event="failed",
                    stage=stage if stage != "process" else "postprocess",
                    request_id=request_id,
                    job_id=job_id,
                    attempt_number=attempts,
                    error_code=classified_code,
                    error_message=str(exc),
                    user_message=classified_message,
                    exc=exc,
                    client=",".join(clients_now) if clients_now else "default",
                    route_alias=route.alias,
                    media_type=media_type,
                    quality=quality,
                    url=cleaned,
                    elapsed_ms=int((time.time() - started) * 1000),
                    origin="external" if classified_code not in {"PROCESS_FAILED", "UNKNOWN", "FFMPEG_FAILED"} else "internal",
                    extra={"final": False},
                )

                can_use_cookies = (
                    cookie_mode != "never"
                    and cookie_state() == "file_present"
                    and not use_cookies
                )
                decision = decide_next(
                    classified_code,
                    stage=stage,
                    attempts=attempts,
                    max_attempts=max_attempts,
                    waits_used=waits_used,
                    max_waits=max_waits,
                    route_switches=route_switches,
                    max_route_switches=max_route_switches,
                    has_next_client=client_index + 1 < len(clients),
                    has_next_route=next_route(route.alias) is not None,
                    can_use_cookies=can_use_cookies,
                    retry_after=retry_after,
                    remaining_seconds=deadline - time.time(),
                )
                if decision.cool_seconds and decision.action in {"fail", "switch_route"}:
                    cool_route(route.alias, decision.cool_seconds)

                if decision.action == "fail":
                    if classified_code == "BOT_CHECK" and use_impersonate and not impersonate_reset:
                        use_impersonate = False
                        impersonate_reset = True
                        clients = [None, ["tv"]]
                        client_index = 0
                        emit_event(
                            event="retry_scheduled",
                            stage=stage,
                            request_id=request_id,
                            job_id=job_id,
                            attempt_number=attempts,
                            error_code=classified_code,
                            strategy="retry_no_impersonate",
                            client="default",
                            route_alias=route.alias,
                            media_type=media_type,
                            quality=quality,
                            url=cleaned,
                            origin="internal",
                        )
                        store.update(job_id, status="retrying", detail="다른 연결 방식으로 재시도 중...", wait_reason="client")
                        continue
                    break
                retry_ms = int((decision.delay or 0) * 1000)
                emit_event(
                    event="retry_scheduled",
                    stage=stage,
                    request_id=request_id,
                    job_id=job_id,
                    attempt_number=attempts,
                    error_code=classified_code,
                    strategy=decision.action,
                    client=",".join(clients_now) if clients_now else "default",
                    route_alias=route.alias,
                    media_type=media_type,
                    quality=quality,
                    url=cleaned,
                    retry_in_ms=retry_ms,
                    origin="internal",
                )
                if decision.action == "use_cookies":
                    use_cookies = True
                    store.update(job_id, status="retrying", detail="저장된 로그인 정보로 다시 시도합니다.", wait_reason="cookies")
                    continue
                if decision.action == "wait":
                    waits_used += 1
                    delay = decision.delay + random.uniform(0.15, 0.9)
                    store.update(
                        job_id,
                        status="retrying",
                        detail="요청 제한으로 대기 중...",
                        wait_reason="rate_limit",
                    )
                    interruptible_sleep(job_id, delay)
                    continue
                if decision.action == "retry_client":
                    client_index += 1
                    store.update(job_id, status="retrying", detail="다른 추출 방식으로 재시도 중...", wait_reason="client")
                    continue
                if decision.action == "switch_route":
                    nxt = next_route(route.alias)
                    if nxt is None:
                        break
                    route = nxt
                    route_switches += 1
                    client_index = 0
                    store.update(
                        job_id,
                        status="retrying",
                        detail="다른 네트워크 경로로 다시 준비 중...",
                        wait_reason="route",
                        route_alias=route.alias,
                    )
                    continue
                if decision.action == "reextract":
                    store.update(job_id, status="retrying", detail="재생 주소를 다시 준비하는 중...", wait_reason="reextract")
                    continue
                if decision.action == "retry_same":
                    store.update(job_id, status="retrying", detail="연결 재시도 중...", wait_reason="network")
                    interruptible_sleep(job_id, decision.delay + random.uniform(0.1, 0.4))
                    continue
                break

        if last_error is None:
            last_error = RuntimeError(last_code)
        _fail_job(job_id, url, media_type, quality, last_error, last_code, last_message)
    except DownloadCancelled:
        store.settle(job_id, "error", error_code="TIMEOUT", error_message=MESSAGES["TIMEOUT"])
        delete_job_dir(job_id)
    except TimeoutError:
        store.settle(job_id, "error", error_code="TIMEOUT", error_message=MESSAGES["TIMEOUT"])
        delete_job_dir(job_id)
    except Exception as exc:
        classified = classify_error(exc)
        _fail_job(job_id, url, media_type, quality, exc, classified.code, classified.user_message)
    finally:
        store.mark_worker(job_id, False)
