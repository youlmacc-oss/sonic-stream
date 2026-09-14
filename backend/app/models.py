from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

MediaType = Literal["video", "audio"]
MediaQuality = Literal["1080p", "4k", "320k", "flac"]
JobStatus = Literal["queued", "downloading", "processing", "done", "error"]


class InspectRequest(BaseModel):
    url: str


class InspectResponse(BaseModel):
    title: str
    author: str
    duration: str
    thumbnail: str


class DownloadRequest(BaseModel):
    url: str
    type: MediaType
    quality: MediaQuality


class DownloadAccepted(BaseModel):
    job_id: str


class ErrorBody(BaseModel):
    code: str
    message: str


class Job:
    def __init__(self, job_id: str, media_type: MediaType, quality: MediaQuality) -> None:
        now = datetime.now(timezone.utc)
        self.id = job_id
        self.media_type = media_type
        self.quality = quality
        self.status: JobStatus = "queued"
        self.percent: float = 0.0
        self.speed: str = "0 KB/s"
        self.eta: int | None = None
        self.detail: str = ""
        self.download_url: str | None = None
        self.file_path: Path | None = None
        self.filename: str | None = None
        self.error_code: str | None = None
        self.error_message: str | None = None
        self.created_at = now
        self.updated_at = now

    def touch(self) -> None:
        self.updated_at = datetime.now(timezone.utc)

    def processing_copy(self) -> str:
        if self.media_type == "audio":
            return "최고 음질 변환 및 앨범 아트 임베딩 중..."
        return "FFmpeg 패키징 및 태그 주입 중..."
