"""
다중 플랫폼 지원을 위한 플랫폼 감지 및 추출기 관리
"""
from __future__ import annotations

import re
from typing import Literal
from urllib.parse import urlparse

# 지원되는 플랫폼 타입
PlatformType = Literal["youtube", "vimeo", "dailymotion", "twitch", "generic"]

class PlatformInfo:
    """플랫폼 정보를 담는 클래스"""
    def __init__(
        self, 
        platform: PlatformType, 
        name: str, 
        icon: str, 
        color: str,
        supports_search: bool = False
    ):
        self.platform = platform
        self.name = name
        self.icon = icon
        self.color = color
        self.supports_search = supports_search

# 플랫폼별 정보 정의
PLATFORMS = {
    "youtube": PlatformInfo(
        platform="youtube",
        name="YouTube",
        icon="📺",
        color="red",
        supports_search=True
    ),
    "vimeo": PlatformInfo(
        platform="vimeo",
        name="Vimeo",
        icon="🎬",
        color="blue",
        supports_search=False
    ),
    "dailymotion": PlatformInfo(
        platform="dailymotion", 
        name="Dailymotion",
        icon="🎭",
        color="orange",
        supports_search=False
    ),
    "twitch": PlatformInfo(
        platform="twitch",
        name="Twitch",
        icon="🟣",
        color="purple", 
        supports_search=False
    ),
    "generic": PlatformInfo(
        platform="generic",
        name="기타 사이트",
        icon="🌐",
        color="gray",
        supports_search=False
    )
}

def detect_platform(url: str) -> PlatformType:
    """
    URL에서 플랫폼을 감지합니다.
    
    Args:
        url: 분석할 URL
        
    Returns:
        감지된 플랫폼 타입
    """
    if not url:
        return "generic"
    
    # URL 정규화
    url = url.strip().lower()
    
    # YouTube 패턴들
    youtube_patterns = [
        r'(?:youtube\.com|youtu\.be)',
        r'youtube-nocookie\.com',
        r'm\.youtube\.com'
    ]
    
    # Vimeo 패턴들  
    vimeo_patterns = [
        r'vimeo\.com',
        r'player\.vimeo\.com'
    ]
    
    # Dailymotion 패턴들
    dailymotion_patterns = [
        r'dailymotion\.com',
        r'dai\.ly'
    ]
    
    # Twitch 패턴들
    twitch_patterns = [
        r'twitch\.tv',
        r'clips\.twitch\.tv',
        r'm\.twitch\.tv'
    ]
    
    # 패턴 매칭
    for pattern in youtube_patterns:
        if re.search(pattern, url):
            return "youtube"
    
    for pattern in vimeo_patterns:
        if re.search(pattern, url):
            return "vimeo"
            
    for pattern in dailymotion_patterns:
        if re.search(pattern, url):
            return "dailymotion"
            
    for pattern in twitch_patterns:
        if re.search(pattern, url):
            return "twitch"
    
    return "generic"

def get_platform_info(platform: PlatformType) -> PlatformInfo:
    """플랫폼 정보를 반환합니다."""
    return PLATFORMS.get(platform, PLATFORMS["generic"])

def get_platform_display_name(url: str) -> str:
    """URL의 플랫폼 표시 이름을 반환합니다."""
    platform = detect_platform(url)
    return get_platform_info(platform).name

def get_platform_icon(url: str) -> str:
    """URL의 플랫폼 아이콘을 반환합니다."""
    platform = detect_platform(url)
    return get_platform_info(platform).icon

def get_platform_color(url: str) -> str:
    """URL의 플랫폼 컬러를 반환합니다."""
    platform = detect_platform(url)
    return get_platform_info(platform).color

def supports_search(platform: PlatformType) -> bool:
    """플랫폼이 검색을 지원하는지 확인합니다."""
    return PLATFORMS.get(platform, PLATFORMS["generic"]).supports_search

def get_search_platforms() -> list[PlatformType]:
    """검색을 지원하는 플랫폼 목록을 반환합니다."""
    return [
        platform for platform, info in PLATFORMS.items() 
        if info.supports_search
    ]

def format_platform_url(url: str) -> dict[str, Any]:
    """
    URL을 플랫폼 정보와 함께 포맷합니다.
    
    Returns:
        {
            'url': str,
            'platform': str,
            'platform_name': str,
            'platform_icon': str,
            'platform_color': str
        }
    """
    platform = detect_platform(url)
    info = get_platform_info(platform)
    
    return {
        'url': url,
        'platform': platform,
        'platform_name': info.name,
        'platform_icon': info.icon,
        'platform_color': info.color
    }