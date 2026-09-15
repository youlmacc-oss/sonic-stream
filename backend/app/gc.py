from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.jobs import store
from app.models import ACTIVE_STATUSES

logger = logging.getLogger("sonicstream.gc")
STALE_DIR_TTL = timedelta(minutes=int(__import__("os").getenv("JOB_DONE_TTL_MINUTES", "10")))


def temp_root() -> Path:
    return Path(tempfile.gettempdir())


def job_dir_for(job_id: str) -> Path:
    return temp_root() / f"sonic_{job_id}"


def job_id_from_dir(path: Path) -> str | None:
    name = path.name
    if not name.startswith("sonic_"):
        return None
    return name.removeprefix("sonic_")


def delete_job_dir(job_id: str) -> None:
    job = store.get(job_id)
    if job is not None and (job.status in ACTIVE_STATUSES or job.worker_alive):
        logger.info("Skip deleting active job dir %s", job_id)
        return
    path = job_dir_for(job_id)
    try:
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
    except OSError as exc:
        logger.warning("Failed to delete %s: %s", path, exc)


def cleanup_job(job_id: str) -> None:
    delete_job_dir(job_id)
    store.remove(job_id)


def sweep_expired() -> None:
    root = temp_root()
    active = store.active_ids()
    cutoff = datetime.now(timezone.utc) - STALE_DIR_TTL
    try:
        entries = list(root.glob("sonic_*"))
    except OSError as exc:
        logger.warning("GC sweep listing failed: %s", exc)
        return

    for entry in entries:
        job_id = job_id_from_dir(entry)
        if job_id and job_id in active:
            continue
        job = store.get(job_id) if job_id else None
        if job is not None and (job.status in ACTIVE_STATUSES or job.worker_alive):
            continue
        if job is not None:
            continue
        try:
            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError as exc:
            logger.warning("GC sweep skipped %s: %s", entry, exc)

    for job_id in store.expired_ids():
        cleanup_job(job_id)
