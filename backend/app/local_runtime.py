from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.runtime import ejs_package_present, js_runtime_status
from app.youtube_auth import cookie_state


def runtime_location() -> str:
    raw = (os.getenv("SONICSTREAM_LOCATION") or "").strip().lower()
    if raw in {"local", "pc", "desktop"}:
        return "local"
    if raw in {"server", "render", "cloud"}:
        return "server"
    if os.getenv("SONICSTREAM_LOCAL", "").strip() in {"1", "true", "yes"}:
        return "local"
    return "server"


def is_local() -> bool:
    return runtime_location() == "local"


def is_loopback_host(host: str) -> bool:
    hostname = host.split(":")[0].strip().lower()
    return hostname in {"127.0.0.1", "localhost", "::1"}


def default_save_dir() -> Path:
    raw = (os.getenv("SONICSTREAM_SAVE_DIR") or "").strip()
    if raw:
        return Path(raw)
    return Path.home() / "Downloads" / "SonicStream"


def unique_dest(directory: Path, name: str) -> Path:
    candidate = directory / name
    if not candidate.exists():
        return candidate
    stem = candidate.stem
    suffix = candidate.suffix
    index = 2
    while True:
        next_path = directory / f"{stem} ({index}){suffix}"
        if not next_path.exists():
            return next_path
        index += 1


def promote_local_file(src: Path, filename: str) -> Path:
    dest_dir = default_save_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_dest(dest_dir, filename)
    shutil.copy2(src, dest)
    return dest


def probe_media(path: Path, ffmpeg_dir: Path | None = None) -> dict[str, Any]:
    ffprobe = "ffprobe"
    if ffmpeg_dir is not None:
        named = ffmpeg_dir / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if named.exists():
            ffprobe = str(named)
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-show_streams",
                "-show_format",
                "-of",
                "json",
                str(path),
            ],
            capture_output=True,
            timeout=20,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return {"ok": False, "error": "ffprobe_unavailable"}
    if completed.returncode != 0:
        return {"ok": False, "error": "ffprobe_failed"}
    try:
        payload = json.loads((completed.stdout or b"{}").decode("utf-8", "replace"))
    except json.JSONDecodeError:
        return {"ok": False, "error": "ffprobe_invalid"}
    streams = payload.get("streams") or []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    width = int(video.get("width") or 0) if video else 0
    height = int(video.get("height") or 0) if video else 0
    duration = None
    try:
        duration = float((payload.get("format") or {}).get("duration") or 0) or None
    except (TypeError, ValueError):
        duration = None
    return {
        "ok": bool(video or audio),
        "has_video": video is not None,
        "has_audio": audio is not None,
        "width": width or None,
        "height": height or None,
        "duration": duration,
        "video_codec": video.get("codec_name") if video else None,
        "audio_codec": audio.get("codec_name") if audio else None,
        "container": (payload.get("format") or {}).get("format_name"),
    }


def runtime_status(ffmpeg_available: bool, ffmpeg_version: str | None = None) -> dict[str, Any]:
    runtimes = js_runtime_status()
    return {
        "location": runtime_location(),
        "save_dir": str(default_save_dir()) if is_local() else None,
        "cookies": cookie_state(),
        "ejs": ejs_package_present(),
        "ffmpeg": ffmpeg_available,
        "ffmpeg_version": ffmpeg_version,
        "runtime": runtimes,
    }
