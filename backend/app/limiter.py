from __future__ import annotations

import os
import threading
import time
from collections import deque
from dataclasses import dataclass


def _int_env(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


@dataclass
class AdmitResult:
    ok: bool
    existing_job_id: str | None = None
    reason: str | None = None


class DownloadLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: set[str] = set()
        self._queue: deque[str] = deque()
        self._fingerprints: dict[str, str] = {}
        self._recent: dict[str, float] = {}

    @property
    def max_active(self) -> int:
        return _int_env("MAX_CONCURRENT_DOWNLOADS", 1)

    @property
    def max_queue(self) -> int:
        return _int_env("MAX_DOWNLOAD_QUEUE", 8)

    def fingerprint(self, url: str, media_type: str, quality: str, owner: str | None = None) -> str:
        base = f"{url.strip()}|{media_type}|{quality}"
        return f"{owner}|{base}" if owner else base

    def admit(self, job_id: str, fingerprint: str) -> AdmitResult:
        now = time.time()
        with self._lock:
            existing = self._fingerprints.get(fingerprint)
            if existing and (existing in self._active or existing in self._queue):
                return AdmitResult(ok=False, existing_job_id=existing, reason="duplicate")
            last = self._recent.get(fingerprint, 0.0)
            if now - last < 3:
                return AdmitResult(ok=False, existing_job_id=existing, reason="duplicate")
            waiting = len(self._queue)
            if len(self._active) >= self.max_active:
                if waiting >= self.max_queue:
                    return AdmitResult(ok=False, reason="busy")
                self._queue.append(job_id)
            else:
                self._active.add(job_id)
            self._fingerprints[fingerprint] = job_id
            self._recent[fingerprint] = now
            return AdmitResult(ok=True)

    def can_run(self, job_id: str) -> bool:
        with self._lock:
            return job_id in self._active

    def promote(self) -> str | None:
        with self._lock:
            while self._queue and len(self._active) < self.max_active:
                nxt = self._queue.popleft()
                self._active.add(nxt)
                return nxt
            return None

    def release(self, job_id: str, fingerprint: str | None = None) -> None:
        with self._lock:
            self._active.discard(job_id)
            try:
                self._queue.remove(job_id)
            except ValueError:
                pass
            if fingerprint and self._fingerprints.get(fingerprint) == job_id:
                self._fingerprints.pop(fingerprint, None)

    def snapshot(self) -> dict[str, int]:
        with self._lock:
            return {
                "active": len(self._active),
                "queued": len(self._queue),
                "max_active": self.max_active,
                "max_queue": self.max_queue,
            }


limiter = DownloadLimiter()
