from __future__ import annotations

import asyncio
import logging
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from app.bundle import build_bundle, bundle_json_bytes, bundle_zip_bytes
from app.env_snapshot import capture_snapshot, current_snapshot, deploy_version, snapshot_id
from app.errors import MESSAGES, raise_api_error
from app.eventlog import emit_event
from app.gc import cleanup_job, delete_job_dir, sweep_expired
from app.jobs import store
from app.limiter import limiter
from app.log_backup import get_backup
from app.log_store import get_store
from app.models import DownloadAccepted, DownloadRequest, InspectRequest, InspectResponse, MediaQuality, MediaType
from app.pot import pot_status
from app.routes import route_status
from app.runtime import ejs_package_present, js_runtime_status
from app.sse import progress_stream
from app.ytdlp_engine import (
    content_disposition,
    ffmpeg_available,
    inspect_url,
    media_type_for,
    resolve_ffmpeg_dir,
    run_download,
    validate_combo,
    validate_url,
)
from app.youtube_auth import auth_status, log_auth_status
from error_logger import log_error, read_backlog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sonicstream")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ffmpeg_dir = resolve_ffmpeg_dir()
    if ffmpeg_dir is not None and ffmpeg_available():
        logger.info("FFmpeg detected at %s", ffmpeg_dir)
    else:
        logger.warning("FFmpeg not found. Muxing and ID3 embedding will fail.")
    log_auth_status()
    logger.info(
        "Job store is in-memory and not shared across processes or instances. "
        "Use a single worker process unless a shared store is added. "
        "Event logs are append-only for one process."
    )
    capture_snapshot()
    get_store().start()
    backup = get_backup()
    backup.enqueue_archives()
    backup.process_pending()
    emit_event(event="started", stage="startup", origin="internal")
    sweep_expired()

    async def ttl_loop() -> None:
        while True:
            await asyncio.sleep(60)
            sweep_expired()
            backup.enqueue_archives()
            backup.process_pending()

    task = asyncio.create_task(ttl_loop())
    yield
    task.cancel()
    get_store().stop()


app = FastAPI(title="SonicStream", lifespan=lifespan)

DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", DEFAULT_ORIGINS)
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or DEFAULT_ORIGINS.split(",")


def admin_token() -> str:
    return (os.getenv("ADMIN_TOKEN") or os.getenv("DEBUG_BACKLOG_TOKEN") or "").strip()


def require_admin(request: Request) -> None:
    token = admin_token()
    if not token:
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Not found", "detail": "Not found"})
    provided = (request.headers.get("X-Admin-Token") or "").strip()
    if not provided or not secrets.compare_digest(provided, token):
        raise HTTPException(
            status_code=401,
            detail={"code": "LOGIN_REQUIRED", "message": "관리자 인증이 필요합니다.", "detail": "관리자 인증이 필요합니다."},
        )


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    if exc.status_code >= 500:
        log_error(
            endpoint=request.url.path,
            error=exc,
            request_data=_request_snapshot(request),
        )
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail and "message" in detail:
        return JSONResponse(status_code=exc.status_code, content=detail)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "code": "PROCESS_FAILED",
            "message": str(detail),
            "detail": str(detail),
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    log_error(
        endpoint=request.url.path,
        error=exc,
        request_data=_request_snapshot(request),
    )
    return JSONResponse(
        status_code=422,
        content={
            "code": "PROCESS_FAILED",
            "message": MESSAGES["PROCESS_FAILED"],
            "detail": MESSAGES["PROCESS_FAILED"],
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    log_error(
        endpoint=request.url.path,
        error=exc,
        request_data=_request_snapshot(request),
    )
    message = MESSAGES["PROCESS_FAILED"]
    return JSONResponse(
        status_code=500,
        content={
            "code": "PROCESS_FAILED",
            "message": message,
            "detail": message,
        },
    )


def _request_snapshot(request: Request, extra: dict[str, object] | None = None) -> dict[str, object]:
    payload: dict[str, object] = {"method": request.method, "path": request.url.path, "request_id": _request_id(request)}
    if extra:
        payload.update(extra)
    return payload


def _request_id(request: Request) -> str:
    incoming = (request.headers.get("X-Request-Id") or "").strip()
    return incoming or str(uuid4())


def _inspect_error_payload(exc: BaseException) -> tuple[str, str]:
    raw = str(exc).strip()
    code, separator, remainder = raw.partition("|")
    if separator and code in MESSAGES:
        return code, remainder.strip() or MESSAGES[code]
    if code in MESSAGES:
        return code, MESSAGES[code]
    return "EXTRACT_FAILED", raw or MESSAGES["EXTRACT_FAILED"]


@app.post("/api/inspect", response_model=InspectResponse)
async def inspect(body: InspectRequest, request: Request) -> InspectResponse:
    request_id = _request_id(request)
    try:
        validate_url(body.url)
    except ValueError:
        raise_api_error("INVALID_URL")

    emit_event(event="started", stage="inspect", request_id=request_id, url=body.url, endpoint="/api/inspect", origin="internal")
    try:
        result = await asyncio.to_thread(inspect_url, body.url)
        emit_event(
            event="succeeded",
            stage="inspect",
            request_id=request_id,
            url=body.url,
            endpoint="/api/inspect",
            extra={"preview_only": result.preview_only},
            origin="internal",
        )
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Inspect failed: %s", exc)
        log_error(
            endpoint="/api/inspect",
            error=exc,
            request_data={"url": body.url, "request_id": request_id},
        )
        code, detail = _inspect_error_payload(exc)
        raise_api_error(code, detail=detail)


@app.post("/api/download", response_model=DownloadAccepted, status_code=202)
async def download(body: DownloadRequest, request: Request) -> DownloadAccepted:
    try:
        validate_url(body.url)
    except ValueError:
        raise_api_error("INVALID_URL")

    try:
        validate_combo(body.type, body.quality)
    except ValueError:
        raise_api_error("PROCESS_FAILED", 422)

    fingerprint = limiter.fingerprint(body.url, body.type, body.quality)
    job_id = str(uuid4())
    request_id = _request_id(request)
    admitted = limiter.admit(job_id, fingerprint)
    if not admitted.ok:
        if admitted.existing_job_id:
            return DownloadAccepted(job_id=admitted.existing_job_id)
        raise_api_error("BUSY")

    store.create(
        job_id,
        body.type,
        body.quality,
        fingerprint=fingerprint,
        request_id=request_id,
        snapshot_id=snapshot_id(),
    )
    emit_event(
        event="started",
        stage="download",
        request_id=request_id,
        job_id=job_id,
        url=body.url,
        media_type=body.type,
        quality=body.quality,
        endpoint="/api/download",
        origin="internal",
    )
    asyncio.create_task(_run_job_safe(job_id, body.url, body.type, body.quality, fingerprint))
    return DownloadAccepted(job_id=job_id)


JOB_TIMEOUT_SECONDS = int(os.getenv("JOB_TIMEOUT_SECONDS", "720"))
QUEUE_WAIT_SECONDS = int(os.getenv("MAX_QUEUE_WAIT_SECONDS", "180"))


async def _run_job_safe(
    job_id: str,
    url: str,
    media_type: MediaType,
    quality: MediaQuality,
    fingerprint: str,
) -> None:
    queue_deadline = asyncio.get_running_loop().time() + QUEUE_WAIT_SECONDS
    while not limiter.can_run(job_id):
        if asyncio.get_running_loop().time() > queue_deadline:
            store.settle(job_id, "error", error_code="BUSY", error_message=MESSAGES["BUSY"])
            limiter.release(job_id, fingerprint)
            limiter.promote()
            return
        current = store.get(job_id)
        if current is None or current.cancel_event.is_set():
            limiter.release(job_id, fingerprint)
            limiter.promote()
            return
        await asyncio.sleep(0.25)

    loop = asyncio.get_running_loop()
    future = loop.run_in_executor(None, run_download, job_id, url, media_type, quality)
    try:
        await asyncio.wait_for(asyncio.shield(future), timeout=JOB_TIMEOUT_SECONDS)
    except asyncio.TimeoutError as exc:
        logger.warning("Job %s timed out; requesting cooperative cancel", job_id)
        store.request_cancel(job_id)
        try:
            await asyncio.wait_for(future, timeout=20)
        except asyncio.TimeoutError:
            logger.warning("Job %s worker still running after cancel grace", job_id)
        current = store.get(job_id)
        if current is None or not current.settled:
            log_error(
                endpoint="/api/download",
                error=exc,
                error_type="TimeoutError",
                error_message=MESSAGES["TIMEOUT"],
                request_data={"job_id": job_id, "url": url, "type": media_type, "quality": quality},
            )
            store.settle(
                job_id,
                "error",
                error_code="TIMEOUT",
                error_message=MESSAGES["TIMEOUT"],
            )
        if future.done():
            delete_job_dir(job_id)
    except Exception as exc:
        logger.exception("Job %s crashed: %s", job_id, exc)
        log_error(
            endpoint="/api/download",
            error=exc,
            request_data={"job_id": job_id, "url": url, "type": media_type, "quality": quality},
        )
        current = store.get(job_id)
        if current is None or not current.settled:
            store.settle(
                job_id,
                "error",
                error_code="PROCESS_FAILED",
                error_message=MESSAGES["PROCESS_FAILED"],
            )
            delete_job_dir(job_id)
    finally:
        limiter.release(job_id, fingerprint)
        limiter.promote()


@app.get("/api/progress/{job_id}")
async def progress(job_id: str, request: Request) -> EventSourceResponse:
    try:
        return EventSourceResponse(
            progress_stream(job_id),
            ping=15,
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as exc:
        log_error(
            endpoint=f"/api/progress/{job_id}",
            error=exc,
            request_data=_request_snapshot(request, {"job_id": job_id}),
        )
        raise


@app.get("/api/fetch/{job_id}")
async def fetch(job_id: str, request: Request) -> FileResponse:
    try:
        job = store.get(job_id)
        if job is None:
            raise_api_error("JOB_NOT_FOUND")
        if job.status != "done" or job.file_path is None:
            raise_api_error("NOT_READY")

        path = Path(job.file_path)
        if not path.exists():
            raise_api_error("JOB_NOT_FOUND")

        filename = job.filename or path.name
        return FileResponse(
            path=str(path),
            media_type=media_type_for(path),
            headers={"Content-Disposition": content_disposition(filename)},
            background=BackgroundTask(cleanup_job, job_id),
        )
    except HTTPException:
        raise
    except Exception as exc:
        log_error(
            endpoint=f"/api/fetch/{job_id}",
            error=exc,
            request_data=_request_snapshot(request, {"job_id": job_id}),
        )
        raise_api_error("PROCESS_FAILED", detail=str(exc))


@app.get("/api/debug/backlog")
async def debug_backlog(request: Request) -> dict[str, object]:
    require_admin(request)
    items = read_backlog(10)
    return {"count": len(items), "items": items}


@app.get("/api/debug/events")
async def debug_events(
    request: Request,
    job_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    limit: int = 200,
) -> dict[str, object]:
    require_admin(request)
    from datetime import datetime

    def parse(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None

    records, meta = get_store().read_records(
        job_id=job_id,
        since=parse(since),
        until=parse(until),
        limit=min(max(1, limit), 2000),
    )
    return {"items": records, "meta": meta}


@app.get("/api/debug/bundle")
async def debug_bundle(
    request: Request,
    job_id: str | None = None,
    since: str | None = None,
    until: str | None = None,
    format: str = "json",
) -> Response:
    require_admin(request)
    if not job_id and not since:
        raise_api_error("INVALID_URL", 400, detail="job_id 또는 since가 필요합니다.")
    bundle = build_bundle(job_id=job_id, since=since, until=until)
    if format == "zip":
        return Response(
            content=bundle_zip_bytes(bundle),
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=diagnostic-bundle.zip"},
        )
    return Response(content=bundle_json_bytes(bundle), media_type="application/json")


@app.get("/api/debug/status")
async def debug_status(request: Request) -> dict[str, object]:
    require_admin(request)
    return {
        "status": "ok",
        "youtube": auth_status(),
        "runtime": js_runtime_status(),
        "ejs": ejs_package_present(),
        "pot": pot_status(),
        "routes": route_status(),
        "limiter": limiter.snapshot(),
        "ffmpeg": ffmpeg_available(),
        "job_store": "in-memory-single-process",
        "logging": get_store().stats(),
        "backup": get_backup().status(),
    }


@app.get("/health")
async def health() -> dict[str, object]:
    return {
        "status": "ok",
        "service": "sonicstream",
        "commit": deploy_version(),
    }


@app.get("/version")
async def version() -> dict[str, object]:
    paths = sorted(
        {
            getattr(route, "path", "")
            for route in app.routes
            if getattr(route, "path", "").startswith("/")
        }
    )
    snapshot = current_snapshot()
    return {
        "service": "sonicstream",
        "commit": deploy_version(),
        "yt_dlp": snapshot.get("yt_dlp"),
        "paths": [path for path in paths if path.startswith("/api") or path in {"/health", "/version"}],
    }
