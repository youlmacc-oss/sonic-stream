from __future__ import annotations

import logging
import shutil
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.jobs import store

logger = logging.getLogger("sonicstream.gc")
TTL = timedelta(minutes=10)


def temp_root() -> Path:
    return Path(tempfile.gettempdir())


def job_dir_for(job_id: str) -> Path:
    return temp_root() / f"sonic_{job_id}"


def delete_job_dir(job_id: str) -> None:
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
    cutoff = datetime.now(timezone.utc) - TTL
    try:
        entries = list(root.glob("sonic_*"))
    except OSError as exc:
        logger.warning("GC sweep listing failed: %s", exc)
        return

    for entry in entries:
        try:
            mtime = datetime.fromtimestamp(entry.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                shutil.rmtree(entry, ignore_errors=True)
        except OSError as exc:
            logger.warning("GC sweep skipped %s: %s", entry, exc)

    for job_id in store.expired_ids():
        cleanup_job(job_id)
