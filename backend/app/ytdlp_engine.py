from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import quote

from yt_dlp import YoutubeDL

from app.errors import MESSAGES, classify_ytdlp_error
from app.gc import delete_job_dir, job_dir_for
from app.jobs import store
from app.models import InspectResponse, MediaQuality, MediaType

logger = logging.getLogger("sonicstream.ytdlp")

URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)
UNSAFE_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
SKIP_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".part", ".ytdl", ".json", ".srt", ".vtt"}
MEDIA_EXTS = {".mp4", ".mp3", ".flac", ".m4a", ".webm", ".mkv", ".mov"}

CHROME_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.7390.122 Safari/537.36"
)

BROWSER_HEADERS = {
    "User-Agent": CHROME_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9,ko;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Google Chrome";v="141", "Chromium";v="141", "Not A(Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Upgrade-Insecure-Requests": "1",
}


# Try yt-dlp defaults first, then known working client sets.
# Forcing only android/web was breaking Render (PO token / SABR).
INSPECT_CLIENT_ATTEMPTS: tuple[list[str] | None, ...] = (
    None,
    ["android", "web"],
    ["tv", "web_safari"],
    ["tv_embedded", "ios", "mweb"],
)
DOWNLOAD_CLIENT_ATTEMPTS: tuple[list[str] | None, ...] = (
    None,
    ["web_safari", "ios"],
    ["android", "web"],
)
YOUTUBE_ID_RE = re.compile(
    r"(?:youtube\.com/(?:watch\?.*?v=|embed/|shorts/|live/|music/)|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})",
    re.IGNORECASE,
)


def base_ydl_opts(**extra: Any) -> dict[str, Any]:
    clients = extra.pop("player_clients", None)
    opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "nocheckcertificate": True,
        "socket_timeout": 25,
        "retries": 2,
        "geo_bypass": True,
        "user_agent": CHROME_UA,
        "http_headers": BROWSER_HEADERS,
        "js_runtimes": {"deno": {}, "node": {}},
        "remote_components": ["ejs:github"],
    }
    if clients:
        opts["extractor_args"] = {"youtube": {"player_client": list(clients)}}
    cookie_file = os.getenv("YOUTUBE_COOKIES_FILE")
    if cookie_file and Path(cookie_file).exists():
        opts["cookiefile"] = cookie_file
    opts.update(extra)
    return opts


def canonicalize_media_url(url: str) -> str:
    match = YOUTUBE_ID_RE.search(url)
    if match:
        return f"https://www.youtube.com/watch?v={match.group(1)}"
    return url


def validate_url(url: str) -> str:
    cleaned = url.strip()
    if not URL_RE.match(cleaned):
        raise ValueError("INVALID_URL")
    return cleaned


def validate_combo(media_type: MediaType, quality: MediaQuality) -> None:
    video_ok = media_type == "video" and quality in {"1080p", "4k"}
    audio_ok = media_type == "audio" and quality in {"320k", "flac"}
    if not (video_ok or audio_ok):
        raise ValueError("PROCESS_FAILED")


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
    opts = base_ydl_opts(skip_download=True, player_clients=clients)
    with YoutubeDL(opts) as ydl:
        return ydl.extract_info(url, download=False) or {}


def inspect_via_oembed(url: str) -> tuple[InspectResponse | None, bool]:
    endpoints = (
        f"https://www.youtube.com/oembed?format=json&url={quote(url, safe='')}",
        f"https://noembed.com/embed?url={quote(url, safe='')}",
    )
    request_headers = {"User-Agent": CHROME_UA, "Accept": "application/json"}
    not_found = False
    for endpoint in endpoints:
        try:
            request = urllib.request.Request(endpoint, headers=request_headers)
            with urllib.request.urlopen(request, timeout=12) as response:
                data = json.loads(response.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                not_found = True
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
            duration="00:00",
            thumbnail=str(data.get("thumbnail_url") or ""),
        ), False
    return None, not_found


def inspect_to_response(info: dict[str, Any]) -> InspectResponse:
    if is_live(info):
        raise RuntimeError(f"LIVE_STREAM|{MESSAGES['LIVE_STREAM']}")
    title = str(info.get("title") or info.get("fulltitle") or "").strip()
    if not title:
        raise RuntimeError(f"NOT_FOUND|{MESSAGES['NOT_FOUND']}")
    return InspectResponse(
        title=title,
        author=pick_author(info),
        duration=format_duration(info.get("duration")),
        thumbnail=pick_thumbnail(info),
    )


def inspect_url(url: str) -> InspectResponse:
    cleaned = canonicalize_media_url(validate_url(url))
    last_error: Exception | None = None
    is_youtube = YOUTUBE_ID_RE.search(cleaned) is not None

    if is_youtube:
        fallback, oembed_missing = inspect_via_oembed(cleaned)
        if fallback is not None:
            return fallback
        if oembed_missing:
            raise RuntimeError(f"NOT_FOUND|{MESSAGES['NOT_FOUND']}")

    for clients in INSPECT_CLIENT_ATTEMPTS:
        try:
            info = inspect_via_ytdlp(cleaned, clients)
            if metadata_thin(info):
                continue
            return inspect_to_response(info)
        except Exception as exc:
            last_error = exc
            label = ",".join(clients) if clients else "default"
            logger.warning("yt-dlp inspect failed (%s) for %s: %s", label, cleaned, exc)

    fallback, oembed_missing = inspect_via_oembed(cleaned)
    if fallback is not None:
        logger.info("Inspect recovered via oEmbed for %s", cleaned)
        return fallback

    if oembed_missing or last_error is None:
        raise RuntimeError(f"NOT_FOUND|{MESSAGES['NOT_FOUND']}")
    code, message = classify_ytdlp_error(last_error)
    raise RuntimeError(f"{code}|{message}") from last_error


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
        status = payload.get("status")
        if status == "downloading":
            total = payload.get("total_bytes") or payload.get("total_bytes_estimate") or 0
            downloaded = payload.get("downloaded_bytes") or 0
            percent = 0.0
            if total:
                percent = min(100.0, downloaded / total * 100.0)
            eta_raw = payload.get("eta")
            eta = int(eta_raw) if isinstance(eta_raw, (int, float)) else None
            store.update(
                job_id,
                status="downloading",
                percent=round(percent, 1),
                speed=format_speed(payload.get("speed")),
                eta=eta,
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
) -> dict[str, Any]:
    outtmpl = str(job_dir / "%(title)s.%(ext)s")
    opts = base_ydl_opts(
        windowsfilenames=True,
        retries=3,
        fragment_retries=3,
        ignoreerrors=False,
        progress_hooks=[make_progress_hook(job_id)],
        outtmpl=outtmpl,
        player_clients=player_clients,
    )
    ffmpeg_dir = resolve_ffmpeg_dir()
    if ffmpeg_dir is not None:
        opts["ffmpeg_location"] = str(ffmpeg_dir)

    if media_type == "video":
        opts.update(
            {
                "format": (
                    "bestvideo[height<=1080]+bestaudio/best[height<=1080]"
                    if quality == "1080p"
                    else "bestvideo[height<=2160]+bestaudio/best"
                ),
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


def resolve_ffmpeg_dir() -> Path | None:
    global _FFMPEG_DIR
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
        if not root.exists():
            continue
        try:
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


def run_download(job_id: str, url: str, media_type: MediaType, quality: MediaQuality) -> None:
    job_dir = job_dir_for(job_id)
    job_dir.mkdir(parents=True, exist_ok=True)
    store.update(job_id, status="downloading", percent=0.0, speed="0 KB/s")

    try:
        cleaned = canonicalize_media_url(validate_url(url))
        last_error: Exception | None = None
        for clients in DOWNLOAD_CLIENT_ATTEMPTS:
            try:
                opts = build_ydl_opts(job_id, media_type, quality, job_dir, player_clients=clients)
                with YoutubeDL(opts) as ydl:
                    info = ydl.extract_info(cleaned, download=False) or {}
                    if is_live(info):
                        raise RuntimeError("LIVE_STREAM")
                    ydl.process_ie_result(info, download=True)
                last_error = None
                break
            except RuntimeError as exc:
                if str(exc) == "LIVE_STREAM":
                    raise
                last_error = exc
                logger.warning("Download attempt failed (%s): %s", clients or "default", exc)
            except Exception as exc:
                last_error = exc
                logger.warning("Download attempt failed (%s): %s", clients or "default", exc)
        if last_error is not None:
            raise last_error

        output = find_media_file(job_dir)
        if output is None:
            raise RuntimeError("PROCESS_FAILED")

        filename = sanitize_filename(output.name)
        store.update(
            job_id,
            status="done",
            percent=100.0,
            file_path=output,
            filename=filename,
            download_url=f"/api/fetch/{job_id}",
            detail="",
        )
    except Exception as exc:
        if str(exc) == "LIVE_STREAM":
            code, message = "LIVE_STREAM", MESSAGES["LIVE_STREAM"]
        elif str(exc) == "PROCESS_FAILED":
            code, message = "PROCESS_FAILED", MESSAGES["PROCESS_FAILED"]
        else:
            code, message = classify_ytdlp_error(exc)
        logger.exception("Job %s failed: %s", job_id, exc)
        store.update(
            job_id,
            status="error",
            error_code=code,
            error_message=message,
        )
        delete_job_dir(job_id)
