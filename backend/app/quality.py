from __future__ import annotations

from typing import Any


def long_short_side(width: object, height: object) -> tuple[int, int]:
    try:
        wide = int(width or 0)
    except (TypeError, ValueError):
        wide = 0
    try:
        high = int(height or 0)
    except (TypeError, ValueError):
        high = 0
    return max(wide, high), min(wide, high)


def quality_caps(quality: str) -> tuple[int, int]:
    if quality == "4k":
        return 3840, 2160
    return 1920, 1080


def format_fits_quality(fmt: dict[str, Any], quality: str) -> bool:
    long_side, short_side = long_short_side(fmt.get("width"), fmt.get("height"))
    cap_long, cap_short = quality_caps(quality)
    return long_side <= cap_long and short_side <= cap_short


def pick_video_format(formats: list[dict[str, Any]], quality: str) -> dict[str, Any] | None:
    videos = [
        item
        for item in formats
        if item.get("vcodec") not in {None, "none"} and (item.get("width") or item.get("height"))
    ]
    fitting = [item for item in videos if format_fits_quality(item, quality)]
    if not fitting:
        return None

    def score(item: dict[str, Any]) -> tuple[int, int, float]:
        long_side, short_side = long_short_side(item.get("width"), item.get("height"))
        try:
            tbr = float(item.get("tbr") or 0)
        except (TypeError, ValueError):
            tbr = 0.0
        return (short_side, long_side, tbr)

    return max(fitting, key=score)


def video_format_selector(quality: str) -> str:
    if quality == "1080p":
        return (
            "bestvideo[height<=1080][width<=1920]+bestaudio/"
            "bestvideo[width<=1080][height<=1920]+bestaudio/"
            "best[height<=1080][width<=1920]/"
            "best[width<=1080][height<=1920]"
        )
    return (
        "bestvideo[height<=2160][width<=3840]+bestaudio/"
        "bestvideo[width<=2160][height<=3840]+bestaudio/"
        "best"
    )
