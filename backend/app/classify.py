from __future__ import annotations

import re
from dataclasses import dataclass

USER_MESSAGES: dict[str, str] = {
    "INVALID_URL": "유효한 동영상 링크를 입력해 주세요.",
    "UNSUPPORTED_URL": "이 주소에서는 받을 수 있는 형식을 찾지 못했습니다.",
    "FORMAT_UNAVAILABLE": "요청한 화질의 재생 형식을 찾지 못했습니다.",
    "ROUTE_CONFIG": "다운로드 네트워크 경로가 설정되지 않았습니다.",
    "ROUTE_COOL": "모든 네트워크 경로가 잠시 휴식 중입니다. 잠시 후 다시 시도해 주세요.",
    "NOT_FOUND": "영상을 찾을 수 없습니다.",
    "GEO_RESTRICTED": "이 영상은 지역 제한으로 받을 수 없습니다.",
    "RATE_LIMITED": "요청이 많아 잠시 대기한 뒤 다시 시도합니다.",
    "BOT_CHECK": "YouTube가 자동 요청 확인을 요구했습니다. 잠시 후 다시 시도해 주세요.",
    "LOGIN_REQUIRED": "로그인이 필요한 영상입니다.",
    "COOKIE_INVALID": "저장된 로그인 정보가 유효하지 않습니다.",
    "POT_MISSING": "이 영상은 추가 확인 토큰이 필요합니다.",
    "POT_FAILED": "확인 토큰 공급에 실패했습니다.",
    "JS_RUNTIME": "영상 보호 처리를 위한 실행 환경이 준비되지 않았습니다.",
    "EXTRACT_FAILED": "영상 정보를 가져오지 못했습니다. 잠시 후 다시 시도해 주세요.",
    "STREAM_FORBIDDEN": "미디어 서버가 재생 주소를 거부했습니다.",
    "STREAM_EXPIRED": "재생 주소가 만료되어 다시 준비합니다.",
    "PROXY_AUTH": "대체 네트워크 경로 인증에 실패했습니다.",
    "PROXY_CONNECT": "대체 네트워크 경로에 연결하지 못했습니다.",
    "NETWORK_ERROR": "네트워크 연결이 불안정합니다. 다시 시도해 주세요.",
    "TIMEOUT": "시간이 초과되었습니다. 다시 시도해 주세요.",
    "LIVE_STREAM": "라이브 스트림은 지원하지 않습니다.",
    "AGE_RESTRICTED": "연령 제한 영상은 받을 수 없습니다.",
    "JOB_NOT_FOUND": "다운로드 작업을 찾을 수 없습니다.",
    "PROCESS_FAILED": "변환에 실패했습니다. 다시 시도해 주세요.",
    "FFMPEG_FAILED": "파일 변환에 실패했습니다.",
    "UNKNOWN": "원인을 특정할 수 없습니다. 다시 시도해 주세요.",
    "NOT_READY": "파일이 아직 준비되지 않았습니다.",
    "BUSY": "다른 다운로드가 진행 중입니다. 잠시 후 다시 시도해 주세요.",
    "AI_UNAVAILABLE": "AI 검색을 쓰려면 OpenAI 키를 이 컴퓨터에 넣어 주세요.",
    "AI_FAILED": "AI 검색을 끝내지 못했습니다. 잠시 후 다시 시도해 주세요.",
    "VERIFY_FAILED": "받은 파일이 손상되었거나 필요한 영상이 없습니다.",
    "VERIFY_UNAVAILABLE": "파일 검사를 할 수 없어 완료로 저장하지 않았습니다.",
    "CANCELLED": "받기를 취소했습니다.",
    "FORBIDDEN": "허용되지 않은 경로입니다.",
    "LOCAL_ONLY": "이 프로그램은 이 PC에 설치해서 사용합니다.",
}

STATUS_BY_CODE: dict[str, int] = {
    "INVALID_URL": 400,
    "UNSUPPORTED_URL": 400,
    "FORMAT_UNAVAILABLE": 422,
    "ROUTE_CONFIG": 503,
    "ROUTE_COOL": 429,
    "NOT_FOUND": 404,
    "GEO_RESTRICTED": 403,
    "RATE_LIMITED": 429,
    "BOT_CHECK": 403,
    "LOGIN_REQUIRED": 401,
    "COOKIE_INVALID": 401,
    "POT_MISSING": 503,
    "POT_FAILED": 503,
    "JS_RUNTIME": 503,
    "EXTRACT_FAILED": 422,
    "STREAM_FORBIDDEN": 403,
    "STREAM_EXPIRED": 409,
    "PROXY_AUTH": 407,
    "PROXY_CONNECT": 502,
    "NETWORK_ERROR": 503,
    "TIMEOUT": 504,
    "LIVE_STREAM": 400,
    "AGE_RESTRICTED": 403,
    "JOB_NOT_FOUND": 404,
    "PROCESS_FAILED": 500,
    "FFMPEG_FAILED": 500,
    "UNKNOWN": 500,
    "NOT_READY": 409,
    "BUSY": 429,
    "AI_UNAVAILABLE": 503,
    "AI_FAILED": 502,
    "VERIFY_FAILED": 422,
    "VERIFY_UNAVAILABLE": 503,
    "CANCELLED": 409,
    "FORBIDDEN": 403,
    "LOCAL_ONLY": 409,
}

TERMINAL_CODES = {
    "INVALID_URL",
    "UNSUPPORTED_URL",
    "NOT_FOUND",
    "GEO_RESTRICTED",
    "LIVE_STREAM",
    "AGE_RESTRICTED",
    "LOGIN_REQUIRED",
    "COOKIE_INVALID",
    "PROXY_AUTH",
    "FFMPEG_FAILED",
    "ROUTE_CONFIG",
    "VERIFY_FAILED",
    "VERIFY_UNAVAILABLE",
    "CANCELLED",
}

WAIT_CODES = {"RATE_LIMITED"}
COOL_ROUTE_CODES = {"BOT_CHECK"}
SWITCH_ROUTE_CODES = {"BOT_CHECK", "STREAM_FORBIDDEN", "PROXY_CONNECT"}
RETRY_NETWORK_CODES = {"NETWORK_ERROR", "TIMEOUT", "STREAM_EXPIRED"}
RETRY_CLIENT_CODES = {"EXTRACT_FAILED", "JS_RUNTIME", "POT_MISSING", "POT_FAILED", "FORMAT_UNAVAILABLE"}


@dataclass(frozen=True)
class ClassifiedError:
    code: str
    message: str
    retry_after: float | None = None
    http_status: int | None = None
    cause_message: str | None = None

    @property
    def user_message(self) -> str:
        return self.message


RETRY_AFTER_RE = re.compile(r"retry-after['\"]?\s*[:=]\s*(\d+(?:\.\d+)?)", re.I)


def parse_retry_after(text: str) -> float | None:
    match = RETRY_AFTER_RE.search(text)
    if not match:
        return None
    try:
        return max(1.0, float(match.group(1)))
    except ValueError:
        return None


def exception_chain_text(exc: BaseException | None) -> str:
    if exc is None:
        return ""
    parts: list[str] = []
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        parts.append(f"{type(current).__name__}: {current}")
        current = current.__cause__ or current.__context__
    return " | ".join(parts)


def http_status_from_exc(exc: BaseException | None) -> int | None:
    current: BaseException | None = exc
    seen: set[int] = set()
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        for attr in ("status", "code", "status_code"):
            value = getattr(current, attr, None)
            if isinstance(value, int) and 100 <= value <= 599:
                return value
        response = getattr(current, "response", None)
        if response is not None:
            for attr in ("status", "status_code", "code"):
                value = getattr(response, attr, None)
                if isinstance(value, int) and 100 <= value <= 599:
                    return value
        current = current.__cause__ or current.__context__
    return None


def classify_error(exc: BaseException, *, stage: str | None = None) -> ClassifiedError:
    text = exception_chain_text(exc) or str(exc)
    lowered = text.lower()
    name = type(exc).__name__.lower()
    retry_after = parse_retry_after(text)
    observed = http_status_from_exc(exc)
    if observed is None:
        from app.diagnostics import extract_http_status

        observed = extract_http_status(text)

    def result(code: str) -> ClassifiedError:
        return ClassifiedError(
            code=code,
            message=USER_MESSAGES.get(code, USER_MESSAGES["UNKNOWN"]),
            retry_after=retry_after,
            http_status=observed,
            cause_message=text[:800],
        )

    if name in {"downloadcancelled", "cancellederror"} or "cancelled" in lowered and "job" in lowered:
        return result("TIMEOUT")
    if "live event" in lowered or "is live" in lowered or "premieres in" in lowered:
        return result("LIVE_STREAM")
    if "age-restricted" in lowered or "confirm your age" in lowered or "may be inappropriate" in lowered:
        return result("AGE_RESTRICTED")
    if "407" in lowered or "proxy authentication" in lowered:
        return result("PROXY_AUTH")
    if "proxy" in lowered and ("refused" in lowered or "connect" in lowered or "tunnel" in lowered):
        return result("PROXY_CONNECT")
    if "429" in lowered or "too many requests" in lowered:
        return result("RATE_LIMITED")
    if (
        "sign in to confirm" in lowered
        or "confirm you’re not a bot" in lowered
        or "confirm you're not a bot" in lowered
        or ("bot" in lowered and "detected" in lowered)
    ):
        return result("BOT_CHECK")
    if "cookie" in lowered and ("expired" in lowered or "invalid" in lowered):
        return result("COOKIE_INVALID")
    if "login_required" in lowered or "sign in to your account" in lowered:
        return result("LOGIN_REQUIRED")
    if "po token" in lowered or "potoken" in lowered or "proof of origin" in lowered:
        if "missing" in lowered or "required" in lowered:
            return result("POT_MISSING")
        return result("POT_FAILED")
    if (
        "javascript runtime" in lowered
        or "js runtime" in lowered
        or "ejs" in lowered and ("missing" in lowered or "required" in lowered)
        or "deno" in lowered and "not found" in lowered
    ):
        return result("JS_RUNTIME")
    if "ffmpeg" in lowered and ("error" in lowered or "failed" in lowered or "not found" in lowered):
        return result("FFMPEG_FAILED")
    if (observed == 403 or "http error 403" in lowered) and (
        "googlevideo" in lowered or "fragment" in lowered or "videoplayback" in lowered
    ):
        return result("STREAM_FORBIDDEN")
    if (observed == 403 or "http error 403" in lowered) and stage == "download":
        return result("STREAM_FORBIDDEN")
    if "expired" in lowered and ("url" in lowered or "signature" in lowered or "n sig" in lowered):
        return result("STREAM_EXPIRED")
    if (
        "not available in your country" in lowered
        or "geographic restrictions" in lowered
        or "blocked it in your country" in lowered
    ):
        return result("GEO_RESTRICTED")
    if (
        "private video" in lowered
        or "has been removed" in lowered
        or "this video is unavailable" in lowered
    ):
        return result("NOT_FOUND")
    if "requested format is not available" in lowered:
        return result("FORMAT_UNAVAILABLE")
    if "no video formats" in lowered:
        return result("FORMAT_UNAVAILABLE")
    if (
        "failed to extract any player response" in lowered
        or "failed to extract player response" in lowered
        or "unable to extract" in lowered
    ):
        return result("EXTRACT_FAILED")
    if "timed out" in lowered or "timeout" in lowered or name == "timeout":
        return result("TIMEOUT")
    if (
        "name or service not known" in lowered
        or "failed to resolve" in lowered
        or "connection reset" in lowered
        or "connection aborted" in lowered
        or "network is unreachable" in lowered
        or "newconnectionerror" in lowered
        or "ssl" in lowered and "error" in lowered
    ):
        return result("NETWORK_ERROR")
    if "unsupported url" in lowered:
        return result("UNSUPPORTED_URL")
    return result("UNKNOWN")
