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
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.background import BackgroundTask

from app.bundle import build_bundle, bundle_json_bytes, bundle_zip_bytes
from app.env_file import load_dotenv_files
from app.env_snapshot import capture_snapshot, current_snapshot, deploy_version, snapshot_id
from app.errors import MESSAGES, raise_api_error
from app.eventlog import emit_event
from app.desktop import (
    open_or_focus_main_window,
    pick_folder_dialog,
    set_autostart,
    set_foreground_window_state,
    set_openai_api_key,
    set_save_dir,
)
from app.history_store import load_history, save_history
from app.installer import installer_file, installer_info, installer_public_url, installer_redirect_url, setup_batch
from app.local_runtime import (
    ManagedFileError,
    is_loopback_host,
    is_local,
    managed_file_stat,
    open_managed_file,
    open_save_folder,
    reveal_managed_file,
    runtime_status,
)
from app.gc import cleanup_job, delete_job_dir, sweep_expired
from app.jobs import store
from app.limiter import limiter
from app.log_backup import get_backup
from app.log_store import get_store
from app.ai_search import AiSearchError, connection_status, run_ai_search
from app import web_session
from app.models import (
    AiSearchRequest,
    AiSearchResponse,
    DownloadAccepted,
    DownloadRequest,
    InspectRequest,
    InspectResponse,
    LocalHistoryRequest,
    LocalOpenRequest,
    LocalSettingsRequest,
    LocalWindowRequest,
    MediaQuality,
    MediaType,
    SearchRequest,
    SearchResponse,
    TranscriptRequest,
    TranscriptResponse,
    WebSessionRequest,
)
from app.transcript import fetch_transcript
from app.pot import pot_status
from app.routes import route_status
from app.runtime import ejs_package_present, js_runtime_status
from app.sse import progress_stream
from app.ui_static import resolve_ui_dir, ui_html_page
from app.ytdlp_engine import (
    content_disposition,
    ffmpeg_available,
    inspect_url,
    media_type_for,
    resolve_ffmpeg_dir,
    run_download,
    search_videos,
    validate_combo,
    validate_url,
)
from app.youtube_auth import auth_status, log_auth_status
from app.download_history import get_history_manager
from error_logger import log_error, read_backlog

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sonicstream")
load_dotenv_files()


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

DEFAULT_ORIGINS = (
    "http://localhost:3000,http://127.0.0.1:3000,"
    "http://localhost:8000,http://127.0.0.1:8000,"
    "https://sonic-stream-teal.vercel.app"
)


def allowed_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", DEFAULT_ORIGINS)
    origins = [origin.strip() for origin in raw.split(",") if origin.strip()]
    return origins or DEFAULT_ORIGINS.split(",")


def admin_token() -> str:
    return (os.getenv("ADMIN_TOKEN") or os.getenv("DEBUG_BACKLOG_TOKEN") or "").strip()


def require_local_desktop(request: Request) -> None:
    if not is_local():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Not found", "detail": "Not found"})
    require_trusted_client(request)


def require_trusted_client(request: Request) -> None:
    if not is_local():
        return
    host = (request.headers.get("host") or "").strip()
    origin = (request.headers.get("origin") or "").strip()
    if host and not is_loopback_host(host):
        raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "로컬 실행만 허용됩니다."})
    if origin:
        from urllib.parse import urlparse

        parsed = urlparse(origin)
        if not is_loopback_host(parsed.hostname or ""):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "허용되지 않은 출처입니다."})


def require_job_access(job: object, request: Request) -> None:
    owner = getattr(job, "owner", None)
    if owner:
        if web_session.current_id(request) != owner:
            raise_api_error("JOB_NOT_FOUND")
        return
    if is_local():
        require_trusted_client(request)
        return
    raise_api_error("JOB_NOT_FOUND")


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


@app.get("/api/status")
async def status(request: Request, response: Response) -> dict[str, str]:
    if is_local():
        return connection_status()
    web_session.bind(request, response)
    return web_session.status_for(request)


@app.post("/api/web/session")
async def web_session_set(body: WebSessionRequest, request: Request, response: Response) -> dict[str, str]:
    if is_local():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Not found", "detail": "Not found"})
    sid = web_session.bind(request, response)
    key = (body.openai_api_key or "").strip()
    if not key.startswith("sk-") or len(key) < 20:
        web_session.remember(sid, key="", openai="key_error", openai_label="AI 키가 올바르지 않습니다")
        return web_session.status_for_id(sid)
    verified = await asyncio.to_thread(web_session.verify_session_key, key)
    web_session.remember(
        sid,
        key=key if verified.get("openai") == "ready" else "",
        openai=verified["openai"],
        openai_label=verified["openai_label"],
    )
    return web_session.status_for_id(sid)


@app.delete("/api/web/session")
async def web_session_clear(request: Request, response: Response) -> dict[str, str]:
    if is_local():
        raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Not found", "detail": "Not found"})
    sid = web_session.bind(request, response)
    web_session.clear(sid)
    return web_session.status_for_id(sid)


@app.get("/api/runtime")
async def runtime(request: Request) -> dict[str, object]:
    snapshot = current_snapshot()
    status = runtime_status(ffmpeg_available())
    status.update(
        {
            "commit": deploy_version(),
            "yt_dlp": snapshot.get("yt_dlp"),
            "location_label": "이 PC" if is_local() else "설치 필요",
            "installer": installer_info(str(request.base_url)),
        }
    )
    return status


@app.get("/api/desktop/installer/info")
async def desktop_installer_info(request: Request) -> dict[str, object]:
    return installer_info(str(request.base_url))


@app.get("/api/desktop/installer")
async def desktop_installer() -> Response:
    path = installer_file()
    if path is not None:
        return FileResponse(
            path=str(path),
            filename="SonicStream-Windows.zip",
            media_type="application/zip",
        )
    redirect = installer_redirect_url() or installer_public_url()
    return RedirectResponse(url=redirect, status_code=307)


@app.get("/api/desktop/setup")
async def desktop_setup(request: Request) -> Response:
    content = setup_batch(installer_public_url(str(request.base_url)))
    return Response(
        content=content.encode("utf-8"),
        media_type="application/octet-stream",
        headers={"Content-Disposition": "attachment; filename=SonicStream-설치.bat"},
    )


@app.get("/api/jobs/{job_id}")
async def job_status(job_id: str, request: Request) -> dict[str, object]:
    job = store.get(job_id)
    if job is None:
        raise_api_error("JOB_NOT_FOUND")
    require_job_access(job, request)
    return {
        "job_id": job.id,
        "status": job.status,
        "percent": job.percent,
        "detail": job.detail,
        "speed": job.speed,
        "eta": job.eta,
        "download_url": job.download_url,
        "saved_path": job.saved_path,
        "file_bytes": job.file_bytes,
        "verified": job.verified,
        "location": job.location,
        "delivery": job.delivery,
        "width": job.actual_width,
        "height": job.actual_height,
        "actual_quality": job.actual_quality,
        "error_code": job.error_code,
        "error_message": job.error_message,
        "filename": job.filename,
    }


def _local_error(exc: ManagedFileError) -> HTTPException:
    status = 404 if exc.code == "NOT_FOUND" else 403 if exc.code == "FORBIDDEN" else 500
    return HTTPException(status_code=status, detail={"code": exc.code, "message": exc.message, "detail": exc.message})


@app.post("/api/local/open")
async def local_open(body: LocalOpenRequest, request: Request) -> dict[str, object]:
    require_local_desktop(request)
    try:
        if body.action == "stat":
            return managed_file_stat(body.path)
        if body.action == "folder":
            if not (body.path or "").strip():
                return open_save_folder()
            return reveal_managed_file(body.path)
        return open_managed_file(body.path)
    except ManagedFileError as exc:
        raise _local_error(exc)


@app.get("/api/local/settings")
async def local_settings_get(request: Request) -> dict[str, object]:
    require_local_desktop(request)
    return runtime_status(ffmpeg_available())


@app.post("/api/local/settings")
async def local_settings_set(body: LocalSettingsRequest, request: Request) -> dict[str, object]:
    require_local_desktop(request)
    try:
        if body.save_dir:
            set_save_dir(body.save_dir)
        if body.autostart is not None:
            set_autostart(body.autostart)
        if body.openai_api_key:
            set_openai_api_key(body.openai_api_key)
    except ManagedFileError as exc:
        raise _local_error(exc)
    return runtime_status(ffmpeg_available())


@app.post("/api/local/pick-folder")
async def local_pick_folder(request: Request) -> dict[str, object]:
    require_local_desktop(request)
    chosen = await asyncio.to_thread(pick_folder_dialog)
    if not chosen:
        return {"ok": False, "cancelled": True}
    try:
        path = set_save_dir(chosen)
    except ManagedFileError as exc:
        raise _local_error(exc)
    return {"ok": True, "save_dir": str(path), **runtime_status(ffmpeg_available())}


@app.post("/api/local/window")
async def local_window(body: LocalWindowRequest, request: Request) -> dict[str, object]:
    require_local_desktop(request)
    try:
        if body.action == "open_main":
            host = (request.headers.get("host") or "").strip() or "127.0.0.1:8011"
            scheme = "https" if request.url.scheme == "https" else "http"
            return await asyncio.to_thread(open_or_focus_main_window, f"{scheme}://{host}/")
        return await asyncio.to_thread(set_foreground_window_state, body.action)
    except ManagedFileError as exc:
        raise _local_error(exc)


@app.get("/api/local/history")
async def local_history_get(request: Request) -> dict[str, object]:
    require_local_desktop(request)
    return {"items": load_history()}


@app.post("/api/local/history")
async def local_history_set(body: LocalHistoryRequest, request: Request) -> dict[str, object]:
    require_local_desktop(request)
    return {"items": save_history(body.items)}


@app.post("/api/local/shutdown")
async def local_shutdown(request: Request) -> dict[str, object]:
    require_local_desktop(request)

    async def stop() -> None:
        await asyncio.sleep(0.4)
        os._exit(0)

    asyncio.create_task(stop())
    return {"ok": True}


@app.get("/api/local/get-openai-key")
async def get_local_openai_key(request: Request) -> dict[str, object]:
    """로컬 환경의 OpenAI 키 정보 반환 (키 값 포함)"""
    require_local_desktop(request)
    
    from app.ai_search import openai_api_key
    
    # 로컬에 설정된 OpenAI API 키 가져오기
    local_key = openai_api_key().strip()
    if not local_key or not local_key.startswith('sk-'):
        return {"available": False, "key": ""}
    
    return {"available": True, "key": local_key}


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, request: Request) -> dict[str, object]:
    job = store.get(job_id)
    if job is None:
        raise_api_error("JOB_NOT_FOUND")
    require_job_access(job, request)
    store.request_cancel(job_id)
    return {"job_id": job_id, "cancel_requested": True}


@app.get("/ai")
async def ai_page() -> FileResponse:
    path = ui_html_page("ai")
    if path is None:
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="text/html; charset=utf-8")


@app.get("/help")
async def help_page() -> FileResponse:
    path = ui_html_page("help")
    if path is None:
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="text/html; charset=utf-8")


@app.get("/install")
async def install_page() -> FileResponse:
    path = ui_html_page("install")
    if path is None:
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="text/html; charset=utf-8")


@app.post("/api/search", response_model=SearchResponse)
async def search(body: SearchRequest) -> SearchResponse:
    try:
        result = await asyncio.to_thread(search_videos, body.query, body.limit)
    except ValueError:
        raise_api_error("INVALID_URL")
    except Exception as exc:
        logger.warning("Search failed: %s", type(exc).__name__)
        raise_api_error("EXTRACT_FAILED")
    return SearchResponse(query=result["query"], items=result["items"])


@app.post("/api/ai-search", response_model=AiSearchResponse)
async def ai_search(body: AiSearchRequest, request: Request, response: Response) -> AiSearchResponse:
    api_key = None
    if is_local():
        require_trusted_client(request)
    else:
        web_session.bind(request, response)
        api_key = web_session.key_for(request)
        if not api_key:
            raise_api_error("AI_UNAVAILABLE")
    try:
        history = [turn.model_dump() for turn in body.history]
        result = await asyncio.to_thread(run_ai_search, body.prompt, history, api_key)
    except ValueError:
        raise_api_error("INVALID_URL")
    except AiSearchError as exc:
        raise_api_error(exc.code)
    except Exception as exc:
        logger.warning("AI search failed: %s", type(exc).__name__)
        raise_api_error("AI_FAILED")
    return AiSearchResponse(reply=result["reply"], keywords=result["keywords"], items=result["items"])


@app.post("/api/transcript", response_model=TranscriptResponse)
async def transcript(body: TranscriptRequest) -> TranscriptResponse:
    try:
        result = await asyncio.to_thread(fetch_transcript, body.url)
    except ValueError:
        raise_api_error("INVALID_URL")
    except Exception as exc:
        logger.warning("Transcript failed: %s", type(exc).__name__)
        raise_api_error("EXTRACT_FAILED")
    return TranscriptResponse(**result)


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
async def download(body: DownloadRequest, request: Request, response: Response) -> DownloadAccepted:
    owner = None
    if is_local():
        require_trusted_client(request)
    else:
        owner = web_session.bind(request, response)
    try:
        validate_url(body.url)
    except ValueError:
        raise_api_error("INVALID_URL")

    try:
        validate_combo(body.type, body.quality)
    except ValueError:
        raise_api_error("PROCESS_FAILED", 422)

    fingerprint = limiter.fingerprint(body.url, body.type, body.quality, owner)
    job_id = str(uuid4())
    request_id = _request_id(request)
    admitted = limiter.admit(job_id, fingerprint)
    if not admitted.ok:
        if admitted.existing_job_id:
            return DownloadAccepted(job_id=admitted.existing_job_id)
        raise_api_error("BUSY")

    # 다운로드 히스토리에 추가
    history_manager = get_history_manager()
    history_manager.add_download(
        url=body.url,
        title="",  # 제목은 나중에 메타데이터 추출 시 업데이트
        media_type=body.type,
        quality=body.quality
    )

    store.create(
        job_id,
        body.type,
        body.quality,
        fingerprint=fingerprint,
        request_id=request_id,
        snapshot_id=snapshot_id(),
        owner=owner,
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
    job = store.get(job_id)
    if job is None:
        raise_api_error("JOB_NOT_FOUND")
    require_job_access(job, request)
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
        require_job_access(job, request)
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


# =============================================================================
# Download History APIs
# =============================================================================

@app.get("/api/downloads/history")
async def get_download_history(
    limit: int = 50,
    status: str | None = None,
    platform: str | None = None
) -> dict[str, Any]:
    """다운로드 히스토리 조회"""
    history_manager = get_history_manager()
    
    # 상태 필터 검증
    status_filter = None
    if status and status in ("pending", "downloading", "completed", "failed", "cancelled"):
        status_filter = status
    
    downloads = history_manager.get_downloads(
        limit=min(limit, 200),  # 최대 200개로 제한
        status_filter=status_filter,
        platform_filter=platform
    )
    
    return {
        "downloads": downloads,
        "total": len(downloads)
    }

@app.get("/api/downloads/stats")
async def get_download_stats() -> dict[str, Any]:
    """다운로드 통계 정보"""
    history_manager = get_history_manager()
    return history_manager.get_download_stats()

@app.post("/api/downloads/cleanup")
async def cleanup_downloads() -> dict[str, Any]:
    """존재하지 않는 파일의 기록 정리"""
    require_local_desktop()
    history_manager = get_history_manager()
    cleaned_count = history_manager.cleanup_missing_files()
    
    return {
        "message": "파일 정리 완료",
        "cleaned_records": cleaned_count
    }

@app.delete("/api/downloads/{url:path}")
async def delete_download_record(url: str, delete_file: bool = False) -> dict[str, Any]:
    """다운로드 기록 삭제"""
    require_local_desktop()
    history_manager = get_history_manager()
    
    # URL 디코딩
    import urllib.parse
    decoded_url = urllib.parse.unquote(url)
    
    success = history_manager.delete_download_record(decoded_url, delete_file)
    
    if success:
        return {"message": "기록이 삭제되었습니다"}
    else:
        raise HTTPException(status_code=404, detail="기록을 찾을 수 없습니다")


_ui_dir = resolve_ui_dir()
if _ui_dir is not None:
    app.mount("/", StaticFiles(directory=str(_ui_dir), html=True), name="ui")
