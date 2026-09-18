from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from app.file_registry import is_registered_file, register_saved_file
from app.runtime import ejs_package_present, js_runtime_status
from app.youtube_auth import cookie_state


def runtime_location() -> str:
    raw = (os.getenv("SONICSTREAM_LOCATION") or "").strip().lower()
    if raw in {"server", "render", "cloud"}:
        return "server"
    if raw in {"local", "pc", "desktop"}:
        return "local"
    if os.getenv("SONICSTREAM_LOCAL", "").strip() in {"1", "true", "yes"}:
        return "local"
    if (os.getenv("SONICSTREAM_UI_DIR") or "").strip():
        return "local"
    try:
        from app.ui_static import resolve_ui_dir

        if resolve_ui_dir() is not None:
            return "local"
    except Exception:
        pass
    return "server"


def is_local() -> bool:
    return runtime_location() == "local"


def is_loopback_host(host: str) -> bool:
    hostname = host.split(":")[0].strip().lower()
    return hostname in {"127.0.0.1", "localhost", "::1"}


def default_save_dir() -> Path:
    from app.desktop import configured_save_dir

    chosen = configured_save_dir()
    if chosen is not None:
        return chosen
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


def promote_local_file(src: Path, filename: str, *, job_id: str | None = None) -> Path:
    dest_dir = default_save_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = unique_dest(dest_dir, filename)
    tmp = dest.with_name(dest.name + ".sspartial")
    try:
        if tmp.exists():
            tmp.unlink()
        shutil.copy2(src, tmp)
        os.replace(tmp, dest)
    except OSError:
        if tmp.exists():
            tmp.unlink(missing_ok=True)
        raise
    register_saved_file(dest, job_id=job_id, bytes_count=dest.stat().st_size)
    return dest


def evaluate_saved_media(
    path: Path,
    media_type: str,
    *,
    source_has_audio: bool | None = None,
    ffmpeg_dir: Path | None = None,
) -> dict[str, Any]:
    if not path.is_file():
        return {"ok": False, "code": "PROCESS_FAILED", "reason": "missing", "probe": {}}
    try:
        size = path.stat().st_size
    except OSError:
        return {"ok": False, "code": "PROCESS_FAILED", "reason": "stat_failed", "probe": {}}
    if size <= 0:
        return {"ok": False, "code": "PROCESS_FAILED", "reason": "empty", "probe": {}, "file_bytes": 0}
    probe = probe_media(path, ffmpeg_dir)
    if probe.get("error") == "ffprobe_unavailable":
        return {"ok": False, "code": "VERIFY_UNAVAILABLE", "reason": "ffprobe_unavailable", "probe": probe, "file_bytes": size}
    if not probe.get("ok"):
        return {"ok": False, "code": "VERIFY_FAILED", "reason": probe.get("error") or "probe_failed", "probe": probe, "file_bytes": size}
    if media_type == "video" and not probe.get("has_video"):
        return {"ok": False, "code": "VERIFY_FAILED", "reason": "missing_video", "probe": probe, "file_bytes": size}
    if media_type == "audio" and not probe.get("has_audio"):
        return {"ok": False, "code": "VERIFY_FAILED", "reason": "missing_audio", "probe": probe, "file_bytes": size}
    if media_type == "video" and source_has_audio is True and not probe.get("has_audio"):
        return {"ok": False, "code": "VERIFY_FAILED", "reason": "missing_audio", "probe": probe, "file_bytes": size}
    return {"ok": True, "code": None, "reason": "ok", "probe": probe, "file_bytes": size}


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


class ManagedFileError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def save_root() -> Path:
    return default_save_dir().expanduser().resolve()


def resolve_managed_file(requested: str) -> Path:
    raw = (requested or "").strip()
    if not raw:
        raise ManagedFileError("NOT_FOUND", "파일을 찾을 수 없습니다.")
    if "\x00" in raw:
        raise ManagedFileError("FORBIDDEN", "허용되지 않은 경로입니다.")
    try:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = save_root() / candidate.name
        if candidate.is_symlink():
            raise ManagedFileError("FORBIDDEN", "바로가기 경로는 열 수 없습니다.")
        resolved = candidate.expanduser().resolve()
    except ManagedFileError:
        raise
    except (OSError, RuntimeError, ValueError) as exc:
        raise ManagedFileError("NOT_FOUND", "파일을 찾을 수 없습니다.") from exc
    if resolved.is_symlink():
        raise ManagedFileError("FORBIDDEN", "바로가기 경로는 열 수 없습니다.")
    if not resolved.is_file():
        raise ManagedFileError("NOT_FOUND", "파일을 찾을 수 없습니다.")
    try:
        resolved.relative_to(save_root())
        return resolved
    except ValueError:
        pass
    if is_registered_file(resolved):
        return resolved
    raise ManagedFileError("FORBIDDEN", "허용된 저장 폴더 안의 파일만 열 수 있습니다.")


def managed_file_stat(requested: str) -> dict[str, Any]:
    path = resolve_managed_file(requested)
    return {
        "ok": True,
        "path": str(path),
        "name": path.name,
        "bytes": path.stat().st_size,
        "folder": str(path.parent),
    }


def open_managed_file(requested: str) -> dict[str, Any]:
    path = resolve_managed_file(requested)
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(path)], check=False, timeout=15)
    except OSError as exc:
        raise ManagedFileError("PROCESS_FAILED", "파일을 열 수 없습니다.") from exc
    return {"ok": True, "path": str(path), "action": "file"}


def reveal_managed_file(requested: str) -> dict[str, Any]:
    path = resolve_managed_file(requested)
    try:
        if os.name == "nt":
            subprocess.run(["explorer.exe", f"/select,{path}"], check=False, timeout=15)
        else:
            subprocess.run(["xdg-open", str(path.parent)], check=False, timeout=15)
    except OSError as exc:
        raise ManagedFileError("PROCESS_FAILED", "저장 폴더를 열 수 없습니다.") from exc
    return {"ok": True, "path": str(path), "action": "folder"}


def open_save_folder() -> dict[str, Any]:
    path = save_root()
    path.mkdir(parents=True, exist_ok=True)
    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.run(["xdg-open", str(path)], check=False, timeout=15)
    except OSError as exc:
        raise ManagedFileError("PROCESS_FAILED", "저장 폴더를 열 수 없습니다.") from exc
    return {"ok": True, "path": str(path), "action": "folder"}


def runtime_status(ffmpeg_available: bool, ffmpeg_version: str | None = None) -> dict[str, Any]:
    from app.desktop import autostart_enabled

    from app.ai_search import connection_status

    runtimes = js_runtime_status()
    ai = connection_status()
    return {
        "location": runtime_location(),
        "save_dir": str(default_save_dir()) if is_local() else None,
        "autostart": autostart_enabled() if is_local() else False,
        "cookies": cookie_state(),
        "ejs": ejs_package_present(),
        "ffmpeg": ffmpeg_available,
        "ffmpeg_version": ffmpeg_version,
        "runtime": runtimes,
        "home": (os.getenv("SONICSTREAM_HOME") or "").strip(),
        "openai": ai.get("openai"),
        "openai_label": ai.get("openai_label"),
        "openai_configured": bool(ai.get("openai") in {"ready", "configured", "checking", "key_error", "quota_error", "network_error"}),
        "openai_verified": ai.get("openai") == "ready",
    }
