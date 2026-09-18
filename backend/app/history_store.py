from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

from app.file_registry import data_dir

_LOCK = threading.Lock()
MAX_ITEMS = 30


def history_path() -> Path:
    return data_dir() / "history.json"


def load_history() -> list[dict[str, Any]]:
    path = history_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = payload.get("items") if isinstance(payload, dict) else payload
    if not isinstance(items, list):
        return []
    cleaned = [item for item in items if isinstance(item, dict) and item.get("id") and item.get("url")]
    return cleaned[:MAX_ITEMS]


def save_history(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    cleaned: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        item_id = str(item.get("id") or "")
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        cleaned.append(item)
        if len(cleaned) >= MAX_ITEMS:
            break
    path = history_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with _LOCK:
        tmp.write_text(json.dumps({"items": cleaned}, ensure_ascii=False, indent=2), encoding="utf-8")
        path.write_bytes(tmp.read_bytes())
        tmp.unlink(missing_ok=True)
    return cleaned
