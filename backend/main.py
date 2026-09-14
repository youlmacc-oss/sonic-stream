from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from app.errors import MESSAGES, raise_api_error
from app.gc import cleanup_job, delete_job_dir, sweep_expired
from app.jobs import store
from app.models import DownloadAccepted, DownloadRequest, InspectRequest, InspectResponse, MediaQuality, MediaType
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sonicstream")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ffmpeg_dir = resolve_ffmpeg_dir()
    if ffmpeg_dir is not None and ffmpeg_available():
        logger.info("FFmpeg detected at %s", ffmpeg_dir)
    else:
        logger.warning("FFmpeg not found. Muxing and ID3 embedding will fail.")
    sweep_expired()

    async def ttl_loop() -> None:
        while True:
            await asyncio.sleep(60)
            sweep_expired()

    task = asyncio.create_task(ttl_loop())
    yield
    task.cancel()


app = FastAPI(title="SonicStream", lifespan=lifespan)

DEFAULT_ORIGINS = "http://localhost:3000,http://127.0.0.1:3000"


def allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", DEFAULT_ORIGINS)
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or DEFAULT_ORIGINS.split(",")


app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def http_exception_handler(_request: Request, exc: HTTPException) -> JSONResponse:
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
async def validation_handler(_request: Request, _exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "PROCESS_FAILED",
            "message": MESSAGES["PROCESS_FAILED"],
            "detail": MESSAGES["PROCESS_FAILED"],
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error: %s", exc)
    message = MESSAGES["PROCESS_FAILED"]
    return JSONResponse(
        status_code=500,
        content={
            "code": "PROCESS_FAILED",
            "message": message,
            "detail": str(exc).strip() or message,
        },
    )


def _inspect_error_payload(exc: BaseException) -> tuple[str, str]:
    raw = str(exc).strip()
    code, separator, remainder = raw.partition("|")
    if separator and code in MESSAGES:
        return code, remainder.strip() or MESSAGES[code]
    if code in MESSAGES:
        return code, MESSAGES[code]
    return "EXTRACT_FAILED", raw or MESSAGES["EXTRACT_FAILED"]


@app.post("/api/inspect", response_model=InspectResponse)
async def inspect(body: InspectRequest) -> InspectResponse:
    try:
        validate_url(body.url)
    except ValueError:
        raise_api_error("INVALID_URL")

    try:
        return await asyncio.to_thread(inspect_url, body.url)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Inspect failed for %s: %s", body.url, exc)
        code, detail = _inspect_error_payload(exc)
        raise_api_error(code, detail=detail)


@app.post("/api/download", response_model=DownloadAccepted, status_code=202)
async def download(body: DownloadRequest) -> DownloadAccepted:
    try:
        validate_url(body.url)
    except ValueError:
        raise_api_error("INVALID_URL")

    try:
        validate_combo(body.type, body.quality)
    except ValueError:
        raise_api_error("PROCESS_FAILED", 422)

    job_id = str(uuid4())
    store.create(job_id, body.type, body.quality)
    asyncio.create_task(_run_job_safe(job_id, body.url, body.type, body.quality))
    return DownloadAccepted(job_id=job_id)


JOB_TIMEOUT_SECONDS = 15 * 60


async def _run_job_safe(job_id: str, url: str, media_type: MediaType, quality: MediaQuality) -> None:
    try:
        await asyncio.wait_for(
            asyncio.to_thread(run_download, job_id, url, media_type, quality),
            timeout=JOB_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        logger.warning("Job %s timed out", job_id)
        store.update(
            job_id,
            status="error",
            error_code="TIMEOUT",
            error_message=MESSAGES["TIMEOUT"],
        )
        delete_job_dir(job_id)
    except Exception as exc:
        logger.exception("Job %s crashed: %s", job_id, exc)
        current = store.get(job_id)
        if current is None or current.status not in {"done", "error"}:
            store.update(
                job_id,
                status="error",
                error_code="PROCESS_FAILED",
                error_message=MESSAGES["PROCESS_FAILED"],
            )
            delete_job_dir(job_id)


@app.get("/api/progress/{job_id}")
async def progress(job_id: str) -> EventSourceResponse:
    return EventSourceResponse(
        progress_stream(job_id),
        ping=15,
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/fetch/{job_id}")
async def fetch(job_id: str) -> FileResponse:
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


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
