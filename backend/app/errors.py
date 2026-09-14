from __future__ import annotations

from typing import NoReturn

from fastapi import HTTPException

MESSAGES: dict[str, str] = {
    "INVALID_URL": "유효한 동영상 링크를 입력해 주세요.",
    "UNSUPPORTED_URL": "지원하지 않는 링크입니다.",
    "NOT_FOUND": "영상을 찾을 수 없습니다.",
    "GEO_RESTRICTED": "이 영상은 지역 제한으로 받을 수 없습니다.",
    "RATE_LIMITED": "요청이 너무 많습니다. 잠시 후 다시 시도해 주세요.",
    "LIVE_STREAM": "라이브 스트림은 지원하지 않습니다.",
    "AGE_RESTRICTED": "연령 제한 영상은 받을 수 없습니다.",
    "NETWORK_ERROR": "네트워크 연결이 끊겼습니다. 다시 시도해 주세요.",
    "JOB_NOT_FOUND": "다운로드 작업을 찾을 수 없습니다.",
    "PROCESS_FAILED": "변환에 실패했습니다. 다시 시도해 주세요.",
    "TIMEOUT": "시간이 초과되었습니다. 다시 시도해 주세요.",
    "NOT_READY": "파일이 아직 준비되지 않았습니다.",
}

STATUS_BY_CODE: dict[str, int] = {
    "INVALID_URL": 400,
    "UNSUPPORTED_URL": 400,
    "NOT_FOUND": 404,
    "GEO_RESTRICTED": 403,
    "RATE_LIMITED": 429,
    "LIVE_STREAM": 400,
    "AGE_RESTRICTED": 403,
    "NETWORK_ERROR": 503,
    "JOB_NOT_FOUND": 404,
    "PROCESS_FAILED": 500,
    "TIMEOUT": 504,
    "NOT_READY": 409,
}


def raise_api_error(code: str, status_code: int | None = None) -> NoReturn:
    raise HTTPException(
        status_code=status_code or STATUS_BY_CODE.get(code, 400),
        detail={"code": code, "message": MESSAGES[code]},
    )


def classify_ytdlp_error(exc: BaseException) -> tuple[str, str]:
    text = str(exc).lower()
    name = type(exc).__name__.lower()

    if "timed out" in text or "timeout" in text or name == "timeout":
        return "TIMEOUT", MESSAGES["TIMEOUT"]
    if "live event" in text or "Premieres in" in str(exc) or "is live" in text:
        return "LIVE_STREAM", MESSAGES["LIVE_STREAM"]
    if (
        "age-restricted" in text
        or "age restricted" in text
        or "confirm your age" in text
        or "may be inappropriate" in text
        or "login_required" in text and "age" in text
    ):
        return "AGE_RESTRICTED", MESSAGES["AGE_RESTRICTED"]
    if (
        "urlopen" in text
        or "network is unreachable" in text
        or "name or service not known" in text
        or "failed to resolve" in text
        or "connection reset" in text
        or "connection aborted" in text
        or "temporarily unavailable" in text
        or "newconnectionerror" in text
    ):
        return "NETWORK_ERROR", MESSAGES["NETWORK_ERROR"]
    if (
        "429" in text
        or "too many requests" in text
        or "sign in to confirm" in text
        or "confirm you’re not a bot" in text
        or "confirm you're not a bot" in text
        or "bot" in text and "detected" in text
    ):
        return "RATE_LIMITED", MESSAGES["RATE_LIMITED"]
    if (
        "not available in your country" in text
        or "not made this video available in your country" in text
        or "geographic restrictions" in text
        or "blocked it in your country" in text
    ):
        return "GEO_RESTRICTED", MESSAGES["GEO_RESTRICTED"]
    if (
        "private video" in text
        or "video unavailable" in text
        or "has been removed" in text
        or "does not exist" in text
        or "incomplete youtube id" in text
    ):
        return "NOT_FOUND", MESSAGES["NOT_FOUND"]
    if "unsupported url" in text or "no video formats" in text:
        return "UNSUPPORTED_URL", MESSAGES["UNSUPPORTED_URL"]
    return "PROCESS_FAILED", MESSAGES["PROCESS_FAILED"]
