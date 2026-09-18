from __future__ import annotations

import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

MediaType = Literal["video", "audio"]
MediaQuality = Literal["best", "720p", "1080p", "4k", "320k", "flac"]
JobStatus = Literal["queued", "retrying", "downloading", "processing", "done", "error"]
ACTIVE_STATUSES = {"queued", "retrying", "downloading", "processing"}


class InspectRequest(BaseModel):
    url: str


class TranscriptRequest(BaseModel):
    url: str


class TranscriptLine(BaseModel):
    start: float
    text: str


class TranscriptResponse(BaseModel):
    url: str
    language: str = ""
    automatic: bool = False
    lines: list[TranscriptLine] = []
    text: str = ""
    error: str = ""
    code: str = ""


class SearchRequest(BaseModel):
    query: str
    limit: int = 30


class SearchHit(BaseModel):
    title: str
    author: str
    url: str
    thumbnail: str
    duration: str
    duration_known: bool = False
    views: str = ""


class SearchResponse(BaseModel):
    query: str
    items: list[SearchHit]


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class AiSearchRequest(BaseModel):
    prompt: str
    history: list[ChatTurn] = []


class AiSearchResponse(BaseModel):
    reply: str
    keywords: list[str]
    items: list[SearchHit]


class InspectResponse(BaseModel):
    title: str
    author: str
    duration: str
    thumbnail: str
    preview_only: bool = False
    duration_known: bool = False
    width: int | None = None
    height: int | None = None
    aspect_ratio: str | None = None
    orientation: str | None = None
    webpage_url: str | None = None


class DownloadRequest(BaseModel):
    url: str
    type: MediaType
    quality: MediaQuality


class DownloadAccepted(BaseModel):
    job_id: str


class LocalOpenRequest(BaseModel):
    path: str = ""
    action: Literal["file", "folder", "stat"] = "file"


class LocalSettingsRequest(BaseModel):
    save_dir: str | None = None
    autostart: bool | None = None
    openai_api_key: str | None = None


class WebSessionRequest(BaseModel):
    openai_api_key: str = ""


class LocalWindowRequest(BaseModel):
    action: Literal["minimize", "maximize", "restore", "open_main"]


class LocalHistoryRequest(BaseModel):
    items: list[dict] = []


class ErrorBody(BaseModel):
    code: str
    message: str


class Job:
    def __init__(
        self,
        job_id: str,
        media_type: MediaType,
        quality: MediaQuality,
        fingerprint: str | None = None,
        request_id: str | None = None,
        snapshot_id: str | None = None,
        owner: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc)
        self.id = job_id
        self.media_type = media_type
        self.quality = quality
        self.fingerprint = fingerprint
        self.request_id = request_id
        self.snapshot_id = snapshot_id
        self.owner = owner
        self.status: JobStatus = "queued"
        self.percent: float = 0.0
        self.speed: str = "0 KB/s"
        self.eta: int | None = None
        self.detail: str = ""
        self.download_url: str | None = None
        self.file_path: Path | None = None
        self.filename: str | None = None
        self.saved_path: str | None = None
        self.file_bytes: int | None = None
        self.verified: bool = False
        from app.local_runtime import runtime_location

        self.location: str = runtime_location()
        self.actual_width: int | None = None
        self.actual_height: int | None = None
        self.actual_quality: str | None = None
        self.delivery: str | None = None
        self.error_code: str | None = None
        self.error_message: str | None = None
        self.attempt: int = 0
        self.route_alias: str | None = None
        self.wait_reason: str | None = None
        self.settled: bool = False
        self.worker_alive: bool = False
        self.cancel_event = threading.Event()
        self.created_at = now
        self.updated_at = now

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def processing_copy(self) -> str:
        if self.media_type == "audio":
            return "최고 음질 변환 및 앨범 아트 임베딩 중..."
        return "FFmpeg 패키징 및 태그 주입 중..."
