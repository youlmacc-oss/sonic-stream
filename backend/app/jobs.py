from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from app.models import ACTIVE_STATUSES, Job, MediaQuality, MediaType

DONE_TTL = timedelta(minutes=int(os.getenv("JOB_DONE_TTL_MINUTES", "10")))
ACTIVE_TTL = timedelta(minutes=int(os.getenv("JOB_ACTIVE_TTL_MINUTES", "30")))


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        import threading
        self._lock = threading.Lock()

    def create(
        self,
        job_id: str,
        media_type: MediaType,
        quality: MediaQuality,
        fingerprint: str | None = None,
        request_id: str | None = None,
        snapshot_id: str | None = None,
    ) -> Job:
        job = Job(
            job_id,
            media_type,
            quality,
            fingerprint=fingerprint,
            request_id=request_id,
            snapshot_id=snapshot_id,
        )
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: object) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.settled:
                return job
            for key, value in fields.items():
                setattr(job, key, value)
            job.touch()
            return job

    def settle(self, job_id: str, status: str, **fields: object) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.settled:
                return None
            for key, value in fields.items():
                setattr(job, key, value)
            job.status = status  # type: ignore[assignment]
            job.settled = status in {"done", "error"}
            job.touch()
            return job

    def request_cancel(self, job_id: str) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.cancel_event.set()

    def mark_worker(self, job_id: str, alive: bool) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return
            job.worker_alive = alive
            job.touch()

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def active_ids(self) -> set[str]:
        with self._lock:
            return {
                job_id
                for job_id, job in self._jobs.items()
                if job.status in ACTIVE_STATUSES or job.worker_alive
            }

    def expired_ids(self) -> list[str]:
        now = datetime.now(timezone.utc)
        with self._lock:
            expired: list[str] = []
            for job_id, job in self._jobs.items():
                if job.worker_alive:
                    continue
                if job.status in ACTIVE_STATUSES:
                    if job.updated_at < now - ACTIVE_TTL:
                        expired.append(job_id)
                    continue
                if job.updated_at < now - DONE_TTL:
                    expired.append(job_id)
            return expired


store = JobStore()
