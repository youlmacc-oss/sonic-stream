from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_LOCK = threading.Lock()


def data_dir() -> Path:
    home = (os.getenv("SONICSTREAM_HOME") or "").strip()
    if home:
        return Path(home) / "data"
    local = (os.getenv("LOCALAPPDATA") or "").strip()
    if local:
        return Path(local) / "SonicStream" / "data"
    return Path.home() / ".sonicstream" / "data"


def registry_path() -> Path:
    return data_dir() / "file-registry.json"


def _load() -> dict[str, Any]:
    path = registry_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"files": []}
    files = payload.get("files")
    if not isinstance(files, list):
        return {"files": []}
    return {"files": files}


def _save(payload: dict[str, Any]) -> None:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def register_saved_file(path: Path, *, job_id: str | None = None, bytes_count: int | None = None) -> dict[str, Any]:
    resolved = path.expanduser().resolve()
    record = {
        "path": str(resolved),
        "bytes": int(bytes_count if bytes_count is not None else resolved.stat().st_size),
        "name": resolved.name,
        "job_id": job_id or "",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        payload = _load()
        files = [item for item in payload["files"] if str(item.get("path") or "") != record["path"]]
        files.insert(0, record)
        payload["files"] = files[:400]
        _save(payload)
    return record


def registered_record(path: Path) -> dict[str, Any] | None:
    try:
        resolved = str(path.expanduser().resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    with _LOCK:
        for item in _load()["files"]:
            if str(item.get("path") or "") == resolved:
                return item if isinstance(item, dict) else None
    return None


def is_registered_file(path: Path) -> bool:
    return registered_record(path) is not None
