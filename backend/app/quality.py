from __future__ import annotations

from typing import Any


def _as_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def format_display_size(fmt: dict[str, Any], rotation: object = 0) -> tuple[int, int]:
    width = _as_int(fmt.get("width"))
    height = _as_int(fmt.get("height"))
    rot = _as_int(fmt.get("rotation") if fmt.get("rotation") not in {None, ""} else rotation)
    if width and height and abs(rot) % 180 == 90:
        width, height = height, width
    return width, height


def long_short_side(width: object, height: object) -> tuple[int, int]:
    wide = _as_int(width)
    high = _as_int(height)
    return max(wide, high), min(wide, high)


def quality_caps(quality: str) -> tuple[int, int]:
    if quality in {"best", "original"}:
        return 100_000, 100_000
    if quality == "4k":
        return 3840, 2160
    if quality == "720p":
        return 1280, 720
    return 1920, 1080


def format_fits_quality(fmt: dict[str, Any], quality: str, rotation: object = 0) -> bool:
    width, height = format_display_size(fmt, rotation)
    long_side, short_side = long_short_side(width, height)
    cap_long, cap_short = quality_caps(quality)
    return long_side <= cap_long and short_side <= cap_short


def _video_candidates(formats: list[dict[str, Any]]) -> list[dict[str, Any]]:
    videos: list[dict[str, Any]] = []
    for item in formats:
        if item.get("vcodec") in {None, "none"}:
            continue
        if item.get("width") or item.get("height"):
            videos.append(item)
    return videos


def _score(item: dict[str, Any], rotation: object = 0) -> tuple[int, int, float]:
    width, height = format_display_size(item, rotation)
    long_side, short_side = long_short_side(width, height)
    try:
        tbr = float(item.get("tbr") or 0)
    except (TypeError, ValueError):
        tbr = 0.0
    return (short_side, long_side, tbr)


def pick_video_format(
    formats: list[dict[str, Any]],
    quality: str,
    rotation: object = 0,
) -> dict[str, Any] | None:
    videos = _video_candidates(formats)
    if not videos:
        return None
    fitting = [item for item in videos if format_fits_quality(item, quality, rotation)]
    if fitting:
        return max(fitting, key=lambda item: _score(item, rotation))
    # Requested cap is below every candidate (e.g. only 4K exists). Do not upscale;
    # take the smallest real video instead of inventing a lower raster.
    return min(videos, key=lambda item: _score(item, rotation))


def select_download_format(
    formats: list[dict[str, Any]],
    quality: str,
    rotation: object = 0,
) -> tuple[dict[str, Any] | None, str]:
    chosen = pick_video_format(formats, quality, rotation)
    if chosen is None:
        return None, video_format_selector(quality)
    fmt_id = str(chosen.get("format_id") or "").strip()
    if not fmt_id:
        return chosen, video_format_selector(quality)
    if chosen.get("acodec") in {None, "none"}:
        return chosen, f"{fmt_id}+bestaudio/{fmt_id}"
    return chosen, fmt_id


def video_format_selector(quality: str) -> str:
    cap_long, _cap_short = quality_caps(quality)
    return (
        f"bestvideo[height<={cap_long}][width<={cap_long}]+bestaudio/"
        f"best[height<={cap_long}][width<={cap_long}]"
    )


def describe_resolution(width: object, height: object) -> str | None:
    wide = _as_int(width)
    high = _as_int(height)
    if wide <= 0 or high <= 0:
        return None
    return f"{wide}×{high}"


def orientation_of(width: object, height: object) -> str | None:
    wide = _as_int(width)
    high = _as_int(height)
    if wide <= 0 or high <= 0:
        return None
    if wide == high:
        return "square"
    return "portrait" if high > wide else "landscape"
