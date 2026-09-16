from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

from app.errors import MESSAGES
from app.jobs import store
from app.models import Job

TICK_SECONDS = 0.2


def snapshot_event(job: Job) -> tuple[str, dict[str, Any]]:
    if job.status == "error":
        return "error", {
            "status": "error",
            "code": job.error_code or "PROCESS_FAILED",
            "message": job.error_message or MESSAGES["PROCESS_FAILED"],
            "job_id": job.id,
        }
    if job.status == "done":
        return "complete", {
            "status": "done",
            "download_url": job.download_url or f"/api/fetch/{job.id}",
            "saved_path": job.saved_path,
            "file_bytes": job.file_bytes,
            "verified": job.verified,
            "location": job.location,
            "delivery": job.delivery or ("local_file" if job.saved_path else "browser"),
            "width": job.actual_width,
            "height": job.actual_height,
            "actual_quality": job.actual_quality,
            "job_id": job.id,
        }
    if job.status == "processing":
        return "processing", {
            "status": "processing",
            "detail": job.detail or job.processing_copy(),
        }
    if job.status == "queued":
        return "queued", {
            "status": "queued",
            "detail": job.detail or "대기열에서 순서를 기다리는 중...",
        }
    if job.status == "retrying":
        return "retrying", {
            "status": "retrying",
            "detail": job.detail or "연결 재시도 중...",
            "wait_reason": job.wait_reason,
            "attempt": job.attempt,
        }
    return "progress", {
        "status": "downloading",
        "percent": job.percent,
        "speed": job.speed,
        "eta": job.eta,
        "attempt": job.attempt,
        "detail": job.detail,
    }


async def progress_stream(job_id: str) -> AsyncIterator[dict[str, str]]:
    job = store.get(job_id)
    if job is None:
        yield {
            "event": "error",
            "data": json.dumps(
                {
                    "status": "error",
                    "code": "JOB_NOT_FOUND",
                    "message": MESSAGES["JOB_NOT_FOUND"],
                },
                ensure_ascii=False,
            ),
        }
        return

    terminal_sent = False
    while True:
        current = store.get(job_id)
        if current is None:
            yield {
                "event": "error",
                "data": json.dumps(
                    {
                        "status": "error",
                        "code": "JOB_NOT_FOUND",
                        "message": MESSAGES["JOB_NOT_FOUND"],
                    },
                    ensure_ascii=False,
                ),
            }
            return

        event_name, payload = snapshot_event(current)
        yield {
            "event": event_name,
            "data": json.dumps(payload, ensure_ascii=False),
        }

        if event_name in {"complete", "error"}:
            if terminal_sent:
                return
            terminal_sent = True
            await asyncio.sleep(TICK_SECONDS)
            return

        await asyncio.sleep(TICK_SECONDS)
