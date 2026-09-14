from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

from app.models import Job, MediaQuality, MediaType

JOB_TTL = timedelta(minutes=10)


class JobStore:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()

    def create(self, job_id: str, media_type: MediaType, quality: MediaQuality) -> Job:
        job = Job(job_id, media_type, quality)
        with self._lock:
            self._jobs[job_id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields: object) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for key, value in fields.items():
                setattr(job, key, value)
            job.touch()
            return job

    def remove(self, job_id: str) -> None:
        with self._lock:
            self._jobs.pop(job_id, None)

    def expired_ids(self) -> list[str]:
        cutoff = datetime.now(timezone.utc) - JOB_TTL
        with self._lock:
            return [
                job_id
                for job_id, job in self._jobs.items()
                if job.updated_at < cutoff
            ]


store = JobStore()
