from __future__ import annotations

import io
import json
import zipfile
from datetime import datetime, timezone
from typing import Any

from app.diagnostics import SCHEMA_VERSION, mask_value
from app.env_snapshot import current_snapshot
from app.eventlog import ANALYSIS_PROMPT
from app.log_store import get_store


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_bundle(
    *,
    job_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 2000,
) -> dict[str, Any]:
    since_dt = _parse_iso(since)
    until_dt = _parse_iso(until)
    records, meta = get_store().read_records(
        job_id=job_id,
        since=since_dt,
        until=until_dt,
        limit=min(max(1, limit), 2000),
    )
    records = [mask_value(item) for item in records]
    failures = [item for item in records if item.get("event") == "failed"]
    finals = [item for item in records if item.get("event") in {"succeeded", "failed", "cancelled"} and item.get("stage") in {"download", "postprocess", "inspect", "fetch"}]
    first = failures[0] if failures else None
    last_fail = failures[-1] if failures else None
    last_event = records[-1] if records else None
    attempts = {item.get("attempt_id") for item in records if item.get("attempt_id")}
    missing: list[str] = []
    if not records:
        missing.append("no_events_in_range")
    if meta.get("incomplete"):
        missing.append("scan_incomplete")
    if any(item.get("schema_version") == 1 for item in records):
        missing.append("legacy_schema_present")
    env = current_snapshot()
    used_snapshot = None
    for item in records:
        if item.get("snapshot_id") == env.get("snapshot_id"):
            used_snapshot = env
            break
    if used_snapshot is None:
        used_snapshot = {"note": "failure-time snapshot not found in this process", "current": env}
        missing.append("environment_snapshot_not_bound")

    reproduction = {
        "job_id": job_id,
        "media_type": next((item.get("media_type") for item in records if item.get("media_type")), None),
        "quality": next((item.get("quality") for item in records if item.get("quality")), None),
        "url": next((item.get("url") for item in records if item.get("url")), None),
        "video_id": next((item.get("video_id") for item in records if item.get("video_id")), None),
        "missing": [item for item in ("cookies_contents", "proxy_secret", "signed_media_url") if True],
    }
    bundle = {
        "manifest": {
            "schema_version": SCHEMA_VERSION,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "job_id": job_id,
            "since": since,
            "until": until,
            "event_count": len(records),
            "incomplete": bool(missing or meta.get("incomplete")),
            "missing": missing,
            "scan": meta,
        },
        "summary": {
            "first_error": _error_brief(first),
            "final_error": _error_brief(last_fail or last_event if last_event and last_event.get("event") == "failed" else last_fail),
            "last_event": last_event.get("event") if last_event else None,
            "last_status": last_event.get("event") if last_event else None,
            "attempts": len(attempts),
        },
        "timeline": records,
        "environment": used_snapshot,
        "errors": [_error_full(item) for item in failures],
        "reproduction": reproduction,
        "analysis_prompt": ANALYSIS_PROMPT,
    }
    return mask_value(bundle)


def bundle_json_bytes(bundle: dict[str, Any]) -> bytes:
    return json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8")


def bundle_zip_bytes(bundle: dict[str, Any]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(bundle.get("manifest", {}), ensure_ascii=False, indent=2))
        archive.writestr("bundle.json", json.dumps(bundle, ensure_ascii=False, indent=2))
        archive.writestr("analysis_prompt.txt", str(bundle.get("analysis_prompt") or ""))
    return buffer.getvalue()


def _error_brief(item: dict[str, Any] | None) -> dict[str, Any] | None:
    if not item:
        return None
    return {
        "event_id": item.get("event_id"),
        "error_code": item.get("error_code"),
        "error_type": item.get("error_type"),
        "error_message": item.get("error_message"),
        "attempt_number": item.get("attempt_number"),
        "stage": item.get("stage"),
    }


def _error_full(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "event_id": item.get("event_id"),
        "timestamp": item.get("timestamp"),
        "attempt_number": item.get("attempt_number"),
        "stage": item.get("stage"),
        "error_code": item.get("error_code"),
        "error_type": item.get("error_type"),
        "http_status": item.get("http_status"),
        "error_message": item.get("error_message"),
        "traceback": item.get("traceback"),
        "origin": item.get("origin"),
    }
