"""
다운로드 히스토리 및 로컬 파일 관리
"""
from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from app.file_registry import data_dir
from app.platform_detector import detect_platform, get_platform_info

logger = logging.getLogger("sonicstream.download_history")

DownloadStatus = Literal["pending", "downloading", "completed", "failed", "cancelled"]

class DownloadRecord:
    """다운로드 기록을 나타내는 클래스"""
    
    def __init__(
        self,
        url: str,
        title: str = "",
        media_type: str = "video",
        quality: str = "best",
        status: DownloadStatus = "pending",
        file_path: str = "",
        file_size: int = 0,
        created_at: str | None = None,
        completed_at: str | None = None,
        error_message: str = "",
    ):
        self.url = url
        self.title = title
        self.media_type = media_type
        self.quality = quality
        self.status = status
        self.file_path = file_path
        self.file_size = file_size
        self.created_at = created_at or datetime.now(timezone.utc).isoformat()
        self.completed_at = completed_at
        self.error_message = error_message
        
        # 플랫폼 정보 자동 설정
        platform = detect_platform(url)
        platform_info = get_platform_info(platform)
        self.platform = platform
        self.platform_name = platform_info.name
        self.platform_icon = platform_info.icon
        self.platform_color = platform_info.color
    
    def to_dict(self) -> dict[str, Any]:
        """딕셔너리 형태로 변환"""
        return {
            "url": self.url,
            "title": self.title,
            "media_type": self.media_type,
            "quality": self.quality,
            "status": self.status,
            "file_path": self.file_path,
            "file_size": self.file_size,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "error_message": self.error_message,
            "platform": self.platform,
            "platform_name": self.platform_name,
            "platform_icon": self.platform_icon,
            "platform_color": self.platform_color,
        }
    
    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> 'DownloadRecord':
        """딕셔너리에서 생성"""
        return cls(
            url=data.get("url", ""),
            title=data.get("title", ""),
            media_type=data.get("media_type", "video"),
            quality=data.get("quality", "best"),
            status=data.get("status", "pending"),
            file_path=data.get("file_path", ""),
            file_size=data.get("file_size", 0),
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
            error_message=data.get("error_message", ""),
        )

class DownloadHistoryManager:
    """다운로드 히스토리를 관리하는 클래스"""
    
    def __init__(self):
        self.history_file = data_dir() / "download_history.json"
        self._ensure_history_file()
    
    def _ensure_history_file(self):
        """히스토리 파일이 없으면 생성"""
        if not self.history_file.exists():
            self.history_file.parent.mkdir(parents=True, exist_ok=True)
            self._save_history([])
    
    def _load_history(self) -> list[DownloadRecord]:
        """히스토리 파일에서 기록 로드"""
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return [DownloadRecord.from_dict(item) for item in data]
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to load download history: %s", exc)
            return []
    
    def _save_history(self, records: list[DownloadRecord]):
        """히스토리를 파일에 저장"""
        try:
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump([record.to_dict() for record in records], f, indent=2, ensure_ascii=False)
        except OSError as exc:
            logger.error("Failed to save download history: %s", exc)
    
    def add_download(self, url: str, title: str = "", media_type: str = "video", quality: str = "best") -> str:
        """새 다운로드를 히스토리에 추가"""
        record = DownloadRecord(
            url=url,
            title=title,
            media_type=media_type,
            quality=quality,
            status="pending"
        )
        
        history = self._load_history()
        history.insert(0, record)  # 최신 기록을 맨 앞에
        
        # 최대 1000개 기록만 유지
        if len(history) > 1000:
            history = history[:1000]
        
        self._save_history(history)
        return record.url  # URL을 ID로 사용
    
    def update_download_status(
        self, 
        url: str, 
        status: DownloadStatus,
        file_path: str = "",
        file_size: int = 0,
        error_message: str = ""
    ):
        """다운로드 상태 업데이트"""
        history = self._load_history()
        
        for record in history:
            if record.url == url:
                record.status = status
                if file_path:
                    record.file_path = file_path
                if file_size:
                    record.file_size = file_size
                if error_message:
                    record.error_message = error_message
                if status == "completed":
                    record.completed_at = datetime.now(timezone.utc).isoformat()
                break
        
        self._save_history(history)
    
    def get_downloads(
        self,
        limit: int = 50,
        status_filter: DownloadStatus | None = None,
        platform_filter: str | None = None
    ) -> list[dict[str, Any]]:
        """다운로드 목록 조회"""
        history = self._load_history()
        
        # 필터 적용
        if status_filter:
            history = [r for r in history if r.status == status_filter]
        
        if platform_filter:
            history = [r for r in history if r.platform == platform_filter]
        
        # 파일 존재 여부 확인
        for record in history:
            if record.file_path and Path(record.file_path).exists():
                record.file_exists = True
                if not record.file_size:
                    try:
                        record.file_size = Path(record.file_path).stat().st_size
                    except OSError:
                        pass
            else:
                record.file_exists = False
        
        return [record.to_dict() for record in history[:limit]]
    
    def get_download_stats(self) -> dict[str, Any]:
        """다운로드 통계 정보"""
        history = self._load_history()
        
        total = len(history)
        completed = len([r for r in history if r.status == "completed"])
        failed = len([r for r in history if r.status == "failed"])
        pending = len([r for r in history if r.status in ("pending", "downloading")])
        
        # 플랫폼별 통계
        platform_stats = {}
        for record in history:
            platform = record.platform
            if platform not in platform_stats:
                platform_stats[platform] = {"count": 0, "completed": 0}
            platform_stats[platform]["count"] += 1
            if record.status == "completed":
                platform_stats[platform]["completed"] += 1
        
        # 총 파일 크기
        total_size = 0
        for record in history:
            if record.file_path and Path(record.file_path).exists():
                try:
                    total_size += Path(record.file_path).stat().st_size
                except OSError:
                    pass
        
        return {
            "total_downloads": total,
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "success_rate": (completed / total * 100) if total > 0 else 0,
            "platform_stats": platform_stats,
            "total_file_size": total_size,
            "total_file_size_mb": total_size / (1024 * 1024),
        }
    
    def cleanup_missing_files(self) -> int:
        """존재하지 않는 파일의 기록을 정리"""
        history = self._load_history()
        cleaned = 0
        
        updated_history = []
        for record in history:
            if record.file_path and not Path(record.file_path).exists():
                if record.status == "completed":
                    record.status = "failed"
                    record.error_message = "파일이 삭제되었음"
                    cleaned += 1
            updated_history.append(record)
        
        self._save_history(updated_history)
        return cleaned
    
    def delete_download_record(self, url: str, delete_file: bool = False) -> bool:
        """다운로드 기록 삭제"""
        history = self._load_history()
        
        for i, record in enumerate(history):
            if record.url == url:
                if delete_file and record.file_path and Path(record.file_path).exists():
                    try:
                        Path(record.file_path).unlink()
                        logger.info("Deleted file: %s", record.file_path)
                    except OSError as exc:
                        logger.warning("Failed to delete file %s: %s", record.file_path, exc)
                
                history.pop(i)
                self._save_history(history)
                return True
        
        return False

# 전역 인스턴스
_history_manager = DownloadHistoryManager()

def get_history_manager() -> DownloadHistoryManager:
    """히스토리 매니저 인스턴스 반환"""
    return _history_manager