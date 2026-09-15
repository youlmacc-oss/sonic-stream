from __future__ import annotations

from typing import Any

from app.eventlog import emit_event
from app.log_store import get_store


def log_error(
    *,
    endpoint: str,
    error: BaseException | None = None,
    error_type: str | None = None,
    error_message: str | None = None,
    request_data: dict[str, Any] | None = None,
) -> None:
    data = request_data or {}
    emit_event(
        event="failed",
        stage=_stage_from_endpoint(endpoint),
        request_id=str(data.get("request_id")) if data.get("request_id") else None,
        job_id=str(data.get("job_id")) if data.get("job_id") else None,
        error_type=error_type,
        error_message=error_message,
        exc=error,
        endpoint=endpoint,
        url=str(data.get("url")) if data.get("url") else None,
        media_type=str(data.get("type")) if data.get("type") else None,
        quality=str(data.get("quality")) if data.get("quality") else None,
        extra={"code": data.get("code")} if data.get("code") else None,
    )


def read_backlog(limit: int = 10) -> list[dict[str, Any]]:
    records, _meta = get_store().read_records(limit=max(1, min(limit, 200)) * 4)
    failures = [item for item in records if item.get("event") == "failed"]
    items: list[dict[str, Any]] = []
    for item in reversed(failures[-max(1, limit):]):
        items.append(
            {
                "timestamp": item.get("timestamp"),
                "endpoint": item.get("endpoint"),
                "request_data": {
                    key: item.get(key)
                    for key in ("job_id", "url", "media_type", "quality")
                    if item.get(key) is not None
                },
                "error_type": item.get("error_type"),
                "error_message": item.get("error_message"),
                "traceback": item.get("traceback") or "[redacted]",
                "event_id": item.get("event_id"),
                "error_code": item.get("error_code"),
            }
        )
    return items


def _stage_from_endpoint(endpoint: str) -> str:
    if "inspect" in endpoint:
        return "inspect"
    if "fetch" in endpoint:
        return "fetch"
    if "progress" in endpoint:
        return "download"
    if "download" in endpoint:
        return "download"
    return "request"
