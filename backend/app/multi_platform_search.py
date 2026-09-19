"""
다중 플랫폼 검색 지원
"""
from __future__ import annotations

import logging
from typing import Any

from yt_dlp import YoutubeDL

from app.platform_detector import PlatformType, detect_platform, format_platform_url
from app.ytdlp_engine import base_ydl_opts, search_ytsearch

logger = logging.getLogger("sonicstream.multi_search")

def search_vimeo(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Vimeo에서 검색합니다."""
    try:
        # Vimeo 검색은 yt-dlp의 vimeo: 접두사 사용
        search_query = f"vimeo:{query}"
        opts = base_ydl_opts(skip_download=True)
        
        with YoutubeDL(opts) as ydl:
            # Vimeo 검색 결과 가져오기
            search_results = ydl.extract_info(
                f"ytsearch{limit}:{search_query}",
                download=False
            )
            
            results = []
            if search_results and 'entries' in search_results:
                for entry in search_results['entries']:
                    if entry:
                        results.append(_format_vimeo_result(entry))
            
            return results[:limit]
            
    except Exception as exc:
        logger.warning("Vimeo search failed: %s", exc)
        return []

def search_dailymotion(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Dailymotion에서 검색합니다."""
    try:
        # Dailymotion 검색
        search_query = f"dailymotion:{query}"
        opts = base_ydl_opts(skip_download=True)
        
        with YoutubeDL(opts) as ydl:
            search_results = ydl.extract_info(
                f"ytsearch{limit}:{search_query}",
                download=False
            )
            
            results = []
            if search_results and 'entries' in search_results:
                for entry in search_results['entries']:
                    if entry:
                        results.append(_format_dailymotion_result(entry))
            
            return results[:limit]
            
    except Exception as exc:
        logger.warning("Dailymotion search failed: %s", exc)
        return []

def _format_vimeo_result(entry: dict[str, Any]) -> dict[str, Any]:
    """Vimeo 검색 결과를 표준 형식으로 변환합니다."""
    url = entry.get('webpage_url', entry.get('url', ''))
    platform_info = format_platform_url(url)
    
    return {
        "title": entry.get('title', 'Unknown Title'),
        "author": entry.get('uploader', entry.get('channel', 'Unknown')),
        "url": url,
        "thumbnail": entry.get('thumbnail', ''),
        "duration": _format_duration(entry.get('duration')),
        "duration_known": entry.get('duration') is not None,
        "views": _format_view_count(entry.get('view_count')),
        "platform": platform_info["platform"],
        "platform_name": platform_info["platform_name"],
        "platform_icon": platform_info["platform_icon"],
        "platform_color": platform_info["platform_color"],
    }

def _format_dailymotion_result(entry: dict[str, Any]) -> dict[str, Any]:
    """Dailymotion 검색 결과를 표준 형식으로 변환합니다."""
    url = entry.get('webpage_url', entry.get('url', ''))
    platform_info = format_platform_url(url)
    
    return {
        "title": entry.get('title', 'Unknown Title'),
        "author": entry.get('uploader', entry.get('channel', 'Unknown')),
        "url": url,
        "thumbnail": entry.get('thumbnail', ''),
        "duration": _format_duration(entry.get('duration')),
        "duration_known": entry.get('duration') is not None,
        "views": _format_view_count(entry.get('view_count')),
        "platform": platform_info["platform"],
        "platform_name": platform_info["platform_name"],
        "platform_icon": platform_info["platform_icon"],
        "platform_color": platform_info["platform_color"],
    }

def _format_duration(duration_seconds: int | None) -> str:
    """초 단위 시간을 MM:SS 또는 HH:MM:SS 형식으로 변환합니다."""
    if duration_seconds is None:
        return ""
    
    hours = duration_seconds // 3600
    minutes = (duration_seconds % 3600) // 60
    seconds = duration_seconds % 60
    
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{minutes:02d}:{seconds:02d}"

def _format_view_count(view_count: int | None) -> str:
    """조회수를 포맷합니다."""
    if view_count is None:
        return ""
    
    if view_count >= 1000000:
        return f"{view_count / 1000000:.1f}M"
    elif view_count >= 1000:
        return f"{view_count / 1000:.1f}K"
    else:
        return str(view_count)

def search_multi_platform(
    query: str, 
    platforms: list[PlatformType] | None = None,
    limit_per_platform: int = 5
) -> list[dict[str, Any]]:
    """
    여러 플랫폼에서 검색을 수행합니다.
    
    Args:
        query: 검색 쿼리
        platforms: 검색할 플랫폼 목록 (None이면 모든 지원 플랫폼)
        limit_per_platform: 플랫폼당 결과 수 제한
        
    Returns:
        통합된 검색 결과 목록
    """
    if platforms is None:
        platforms = ["youtube", "vimeo", "dailymotion"]
    
    all_results = []
    
    for platform in platforms:
        try:
            if platform == "youtube":
                results = search_ytsearch(query, limit_per_platform)
            elif platform == "vimeo":
                results = search_vimeo(query, limit_per_platform)
            elif platform == "dailymotion":
                results = search_dailymotion(query, limit_per_platform)
            else:
                continue
                
            all_results.extend(results)
            
        except Exception as exc:
            logger.warning("Search failed for platform %s: %s", platform, exc)
            continue
    
    return all_results

def enhanced_search(query: str, limit: int = 15) -> dict[str, Any]:
    """
    개선된 다중 플랫폼 검색.
    
    기본적으로 YouTube를 메인으로 하고, 다른 플랫폼 결과도 포함합니다.
    """
    # URL인지 확인
    if query.strip().startswith(("http://", "https://")):
        # URL인 경우 해당 플랫폼만 처리
        platform = detect_platform(query)
        return {
            "query": query,
            "items": [],  # URL 직접 처리는 별도 로직에서
            "platforms_searched": [platform]
        }
    
    # 검색어인 경우 다중 플랫폼 검색
    # YouTube 우선으로 더 많은 결과, 다른 플랫폼은 적게
    youtube_results = search_ytsearch(query, limit - 5)  # YouTube에서 대부분
    other_results = []
    
    # 추가 플랫폼에서 적은 수의 결과 가져오기
    try:
        vimeo_results = search_vimeo(query, 3)
        other_results.extend(vimeo_results)
    except Exception:
        pass
    
    try:
        dailymotion_results = search_dailymotion(query, 2) 
        other_results.extend(dailymotion_results)
    except Exception:
        pass
    
    # 결과 통합
    all_items = youtube_results + other_results
    
    return {
        "query": query,
        "items": all_items[:limit],
        "platforms_searched": ["youtube", "vimeo", "dailymotion"],
        "total_found": len(all_items)
    }