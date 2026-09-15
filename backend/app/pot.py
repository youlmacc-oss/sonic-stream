from __future__ import annotations

import logging
import os
import time
from typing import Any
from urllib.parse import urlparse
from urllib.request import urlopen

logger = logging.getLogger("sonicstream.pot")
_reach_cache: tuple[float, bool | None] | None = None


def pot_base_url() -> str | None:
    raw = (os.getenv("YOUTUBE_POT_BASE_URL") or os.getenv("BGUTIL_PROVIDER") or "").strip()
    return raw.rstrip("/") or None


def pot_plugin_loaded() -> bool:
    from importlib.util import find_spec

    return find_spec("yt_dlp_plugins.extractor.getpot_bgutil_http") is not None


def pot_reachable(timeout: float = 1.5) -> bool | None:
    global _reach_cache
    base = pot_base_url()
    if not base:
        return None
    if _reach_cache and time.time() - _reach_cache[0] < 20:
        return _reach_cache[1]
    parsed = urlparse(base)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        _reach_cache = (time.time(), False)
        return False
    try:
        with urlopen(f"{base}/ping", timeout=timeout) as response:
            reachable = 200 <= response.status < 500
    except Exception:
        reachable = False
    _reach_cache = (time.time(), reachable)
    return reachable


def pot_ready() -> bool:
    return pot_plugin_loaded() and pot_reachable() is True


def apply_pot(opts: dict[str, Any]) -> dict[str, Any]:
    base = pot_base_url()
    if not base or not pot_plugin_loaded():
        return opts
    extractor_args = opts.setdefault("extractor_args", {})
    extractor_args.setdefault("youtubepot-bgutilhttp", {})["base_url"] = [base]
    return opts


def pot_status() -> dict[str, object]:
    return {
        "configured": pot_base_url() is not None,
        "plugin": pot_plugin_loaded(),
        "reachable": pot_reachable() if pot_base_url() else None,
    }
