from __future__ import annotations

from fastapi import HTTPException

from app.classify import STATUS_BY_CODE, USER_MESSAGES, classify_error

MESSAGES = USER_MESSAGES
ERROR_MESSAGES = USER_MESSAGES


def classify_download_error(exc: Exception) -> tuple[str, str]:
    classified = classify_error(exc)
    return classified.code, classified.user_message


def classify_ytdlp_error(exc: Exception) -> tuple[str, str]:
    return classify_download_error(exc)


def raise_api_error(
    code: str,
    status: int | None = None,
    detail: str | None = None,
) -> None:
    message = detail or MESSAGES.get(code, MESSAGES["UNKNOWN"])
    raise HTTPException(
        status_code=status or STATUS_BY_CODE.get(code, 500),
        detail={"code": code, "message": message, "detail": message},
    )
