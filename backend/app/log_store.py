from __future__ import annotations

import gzip
import json
import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from queue import Empty, Full, Queue
from typing import Any

from app.diagnostics import SCHEMA_VERSION, mask_value

DEFAULT_QUEUE_SIZE = 1000
DEFAULT_MAX_BYTES = 5_000_000
DEFAULT_RETAIN_DAYS = 14
DEFAULT_MAX_TOTAL = 50_000_000
FLUSH_JOIN_SECONDS = 5.0
CRITICAL_EVENTS = {"failed", "cancelled", "succeeded"}
EMERGENCY_LIMIT_FACTOR = 5


def default_log_dir() -> Path:
    raw = (os.getenv("SONIC_LOG_DIR") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent.parent / "logs"


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


class EventStore:
    def __init__(self, directory: Path | None = None) -> None:
        self.directory = directory or default_log_dir()
        self.current_path = self.directory / "events.jsonl"
        self.legacy_path = self.directory / "error_backlog.jsonl"
        self.max_bytes = _int_env("LOG_ROTATE_MAX_BYTES", DEFAULT_MAX_BYTES)
        self.retain_days = _int_env("LOG_RETAIN_DAYS", DEFAULT_RETAIN_DAYS)
        self.max_total_bytes = _int_env("LOG_MAX_TOTAL_BYTES", DEFAULT_MAX_TOTAL)
        self.queue_size = _int_env("LOG_QUEUE_SIZE", DEFAULT_QUEUE_SIZE)
        self._queue: Queue[dict[str, Any] | None] = Queue(maxsize=self.queue_size)
        self._lock = threading.Lock()
        self._writer: threading.Thread | None = None
        self._stop = threading.Event()
        self.dropped = 0
        self.write_failures = 0
        self.last_write_error: str | None = None
        self.last_rotate_at: str | None = None
        self._busy = False

    def start(self) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        if self._writer is not None and self._writer.is_alive():
            return
        self._stop.clear()
        self._writer = threading.Thread(target=self._run, name="sonic-eventlog", daemon=True)
        self._writer.start()

    def stop(self, timeout: float = FLUSH_JOIN_SECONDS) -> None:
        self._stop.set()
        try:
            self._queue.put(None, timeout=min(1.0, timeout))
        except (Full, Exception):
            try:
                self._queue.put_nowait(None)
            except (Full, Exception):
                pass
        if self._writer is not None:
            self._writer.join(timeout=timeout)
        leftover: list[dict[str, Any]] = []
        while True:
            try:
                item = self._queue.get_nowait()
            except Empty:
                break
            if item is not None:
                leftover.append(item)
        for item in leftover:
            try:
                self._append(item)
            except Exception as exc:
                self.write_failures += 1
                self.last_write_error = type(exc).__name__

    def emit(self, record: dict[str, Any], *, urgent: bool = False) -> bool:
        event = str(record.get("event") or "")
        if urgent or event in CRITICAL_EVENTS:
            try:
                self._append(record)
                return True
            except Exception as exc:
                self.write_failures += 1
                self.last_write_error = type(exc).__name__
                try:
                    self._queue.put_nowait(record)
                    return True
                except Full:
                    self.dropped += 1
                    return False
        try:
            self._queue.put_nowait(record)
            return True
        except Full:
            self.dropped += 1
            return False
        except Exception:
            self.dropped += 1
            return False

    def _run(self) -> None:
        while not self._stop.is_set() or not self._queue.empty():
            try:
                item = self._queue.get(timeout=0.2)
            except Empty:
                continue
            if item is None:
                continue
            try:
                self._busy = True
                self._append(item)
            except Exception as exc:
                self.write_failures += 1
                self.last_write_error = type(exc).__name__
            finally:
                self._busy = False

    def _append(self, record: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        line = json.dumps(mask_value(record), ensure_ascii=False) + "\n"
        with self._lock:
            with self.current_path.open("a", encoding="utf-8") as handle:
                handle.write(line)
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
            self._maybe_rotate_locked()
            self._enforce_limits_locked()

    def _maybe_rotate_locked(self) -> None:
        if not self.current_path.exists():
            return
        try:
            size = self.current_path.stat().st_size
        except OSError:
            return
        if size < self.max_bytes:
            return
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = self.directory / f"events-{stamp}.jsonl"
        if dest.exists():
            dest = self.directory / f"events-{stamp}-{int(time.time() * 1000)}.jsonl"
        try:
            self.current_path.replace(dest)
        except OSError:
            return
        self.last_rotate_at = datetime.now(timezone.utc).isoformat()
        self._compress(dest)

    def _compress(self, path: Path) -> Path | None:
        gz = path.with_suffix(path.suffix + ".gz")
        if gz.exists():
            gz = path.with_name(f"{path.stem}-{int(time.time())}.jsonl.gz")
        try:
            with path.open("rb") as source, gzip.open(gz, "wb") as target:
                shutil.copyfileobj(source, target)
            if gz.exists() and gz.stat().st_size > 0:
                path.unlink(missing_ok=True)
                return gz
        except OSError as exc:
            self.write_failures += 1
            self.last_write_error = type(exc).__name__
        return None

    def _backup_configured(self) -> bool:
        return bool((os.getenv("LOG_BACKUP_DIR") or "").strip())

    def _backed_up_keys(self) -> set[str]:
        index = self.directory / "backup_index.json"
        if not index.exists():
            return set()
        try:
            data = json.loads(index.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        copied = data.get("copied") if isinstance(data, dict) else None
        if not isinstance(copied, dict):
            return set()
        return {str(key) for key in copied}

    def _may_delete_archive(self, path: Path, *, emergency: bool) -> bool:
        if path.resolve() == self.current_path.resolve():
            return False
        if not self._backup_configured():
            return True
        try:
            key = str(path.resolve())
        except OSError:
            return emergency
        if key in self._backed_up_keys():
            return True
        return emergency

    def _enforce_limits_locked(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(days=self.retain_days)
        archives = self.archive_files()
        for path in archives:
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            except OSError:
                continue
            if mtime < cutoff and self._may_delete_archive(path, emergency=False):
                try:
                    path.unlink()
                except OSError:
                    continue
        archives = self.archive_files()
        total = 0
        try:
            if self.current_path.exists():
                total += self.current_path.stat().st_size
        except OSError:
            pass
        sized = []
        for path in archives:
            try:
                sized.append((path.stat().st_mtime, path.stat().st_size, path))
                total += path.stat().st_size
            except OSError:
                continue
        sized.sort()
        emergency_bytes = self.max_total_bytes * EMERGENCY_LIMIT_FACTOR
        while total > self.max_total_bytes and sized:
            _, size, path = sized[0]
            emergency = total > emergency_bytes
            if not self._may_delete_archive(path, emergency=emergency):
                sized.pop(0)
                continue
            sized.pop(0)
            try:
                path.unlink()
                total -= size
            except OSError:
                break

    def archive_files(self) -> list[Path]:
        files = list(self.directory.glob("events-*.jsonl")) + list(self.directory.glob("events-*.jsonl.gz"))
        return sorted(files, key=lambda path: path.name)

    def iter_sources(self, include_legacy: bool = True) -> list[Path]:
        sources: list[Path] = []
        if self.current_path.exists():
            sources.append(self.current_path)
        sources.extend(self.archive_files())
        if include_legacy and self.legacy_path.exists():
            sources.append(self.legacy_path)
        return sources

    def parse_line(self, line: str) -> dict[str, Any] | None:
        text = line.strip()
        if not text:
            return None
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(parsed, dict):
            return None
        if "schema_version" not in parsed:
            parsed["schema_version"] = 1
        return parsed

    def read_records(
        self,
        *,
        job_id: str | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        limit: int = 2000,
        max_files: int = 40,
        max_seconds: float = 8.0,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        started = time.time()
        records: list[dict[str, Any]] = []
        skipped = 0
        truncated = False
        scanned = 0
        for path in self.iter_sources()[:max_files]:
            if time.time() - started > max_seconds:
                truncated = True
                break
            try:
                with self._open_text(path) as handle:
                    for line in handle:
                        scanned += 1
                        parsed = self.parse_line(line)
                        if parsed is None:
                            skipped += 1
                            continue
                        if job_id and parsed.get("job_id") != job_id:
                            continue
                        stamp = _parse_ts(parsed.get("timestamp"))
                        if since and stamp and stamp < since:
                            continue
                        if until and stamp and stamp > until:
                            continue
                        records.append(parsed)
                        if len(records) >= limit:
                            truncated = True
                            break
            except OSError:
                skipped += 1
            if truncated:
                break
        records.sort(key=lambda item: str(item.get("timestamp") or ""))
        return records, {
            "scanned_lines": scanned,
            "skipped_lines": skipped,
            "truncated": truncated,
            "incomplete": truncated or skipped > 0,
        }

    def flush(self, timeout: float = 3.0) -> None:
        deadline = time.time() + timeout
        while (not self._queue.empty() or self._busy) and time.time() < deadline:
            time.sleep(0.02)
        time.sleep(0.05)

    def _open_text(self, path: Path):
        if path.name.endswith(".gz"):
            return gzip.open(path, "rt", encoding="utf-8", errors="replace")
        return path.open("rt", encoding="utf-8", errors="replace")

    def read_file(self, path: Path) -> list[dict[str, Any]]:
        records: list[dict[str, Any]] = []
        try:
            with self._open_text(path) as handle:
                for line in handle:
                    parsed = self.parse_line(line)
                    if parsed is not None:
                        records.append(parsed)
        except OSError:
            return records
        return records

    def stats(self) -> dict[str, Any]:
        return {
            "directory": str(self.directory),
            "current": self.current_path.name,
            "dropped": self.dropped,
            "write_failures": self.write_failures,
            "last_write_error": self.last_write_error,
            "last_rotate_at": self.last_rotate_at,
            "queue_size": self.queue_size,
            "queued": self._queue.qsize(),
            "schema_version": SCHEMA_VERSION,
            "single_process": True,
        }


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


_STORE: EventStore | None = None
_STORE_LOCK = threading.Lock()


def get_store() -> EventStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is None:
            _STORE = EventStore()
            _STORE.start()
        return _STORE


def reset_store(directory: Path | None = None) -> EventStore:
    global _STORE
    with _STORE_LOCK:
        if _STORE is not None:
            _STORE.stop(timeout=1.0)
        _STORE = EventStore(directory)
        _STORE.start()
        return _STORE
