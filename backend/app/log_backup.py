from __future__ import annotations

import json
import os
import shutil
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.env_snapshot import instance_id
from app.log_store import EventStore, get_store

APP_NAME = "sonic-stream"


def backup_root() -> Path | None:
    raw = (os.getenv("LOG_BACKUP_DIR") or "").strip()
    return Path(raw) if raw else None


class LogBackup:
    def __init__(self, store: EventStore | None = None) -> None:
        self.store = store or get_store()
        self._lock = threading.Lock()
        self.last_success_at: str | None = None
        self.last_failure: str | None = None
        self.pending_count = 0
        self.index_path = self.store.directory / "backup_index.json"

    def enabled(self) -> bool:
        return backup_root() is not None

    def _index(self) -> dict[str, Any]:
        if not self.index_path.exists():
            return {"copied": {}, "pending": []}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"copied": {}, "pending": []}
        if not isinstance(data, dict):
            return {"copied": {}, "pending": []}
        data.setdefault("copied", {})
        data.setdefault("pending", [])
        return data

    def _save_index(self, data: dict[str, Any]) -> None:
        self.store.directory.mkdir(parents=True, exist_ok=True)
        tmp = self.index_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.index_path)

    def destination_for(self, source: Path) -> Path:
        root = backup_root()
        if root is None:
            raise RuntimeError("backup_disabled")
        day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        unique = f"{source.stem}-{uuid.uuid4().hex[:10]}{''.join(source.suffixes)}"
        return root / APP_NAME / day / instance_id() / unique

    def enqueue_archives(self) -> None:
        if not self.enabled():
            return
        with self._lock:
            data = self._index()
            copied = data.get("copied", {})
            pending = list(data.get("pending", []))
            for path in self.store.archive_files():
                key = str(path.resolve())
                if key in copied or key in pending:
                    continue
                pending.append(key)
            data["pending"] = pending
            self.pending_count = len(pending)
            self._save_index(data)

    def process_pending(self, retries: int = 2) -> int:
        if not self.enabled():
            return 0
        copied_count = 0
        with self._lock:
            data = self._index()
            pending = list(data.get("pending", []))
            remaining: list[str] = []
            copied = dict(data.get("copied", {}))
            for key in pending:
                source = Path(key)
                if not source.exists():
                    continue
                if key in copied:
                    continue
                ok = False
                last_error = None
                dest = self.destination_for(source)
                for _ in range(max(1, retries)):
                    try:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(source, dest)
                        if dest.exists() and dest.stat().st_size == source.stat().st_size:
                            copied[key] = {
                                "dest": str(dest),
                                "copied_at": datetime.now(timezone.utc).isoformat(),
                                "size": dest.stat().st_size,
                            }
                            ok = True
                            break
                    except OSError as exc:
                        last_error = type(exc).__name__
                if ok:
                    copied_count += 1
                    self.last_success_at = datetime.now(timezone.utc).isoformat()
                    self.last_failure = None
                else:
                    remaining.append(key)
                    self.last_failure = last_error or "copy_failed"
            data["copied"] = copied
            data["pending"] = remaining
            self.pending_count = len(remaining)
            self._save_index(data)
        return copied_count

    def restore_file(self, dest: Path) -> list[dict[str, Any]]:
        return self.store.read_file(dest)

    def status(self) -> dict[str, Any]:
        root = backup_root()
        return {
            "enabled": self.enabled(),
            "directory": str(root) if root else None,
            "pending": self.pending_count,
            "last_success_at": self.last_success_at,
            "last_failure": self.last_failure,
            "note": (
                "Operator-configured local/volume copy. Remote object storage is not configured."
                if self.enabled()
                else "Backup is not active. Redeploys can drop local logs."
            ),
        }


_BACKUP: LogBackup | None = None


def get_backup() -> LogBackup:
    global _BACKUP
    if _BACKUP is None:
        _BACKUP = LogBackup()
    return _BACKUP
