from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.classify import RETRY_CLIENT_CODES, RETRY_NETWORK_CODES, SWITCH_ROUTE_CODES, TERMINAL_CODES

Action = Literal["fail", "wait", "retry_same", "retry_client", "switch_route", "reextract", "use_cookies"]


@dataclass(frozen=True)
class AttemptDecision:
    action: Action
    delay: float = 0.0
    cool_seconds: float = 0.0


def backoff_delay(waits_used: int, retry_after: float | None) -> float:
    if retry_after is not None:
        return min(120.0, max(1.0, retry_after))
    return min(60.0, (2 ** waits_used) + 0.35)


def decide_next(
    code: str,
    *,
    stage: str,
    attempts: int,
    max_attempts: int,
    waits_used: int,
    max_waits: int,
    route_switches: int,
    max_route_switches: int,
    has_next_client: bool,
    has_next_route: bool,
    can_use_cookies: bool,
    retry_after: float | None = None,
) -> AttemptDecision:
    if attempts >= max_attempts:
        return AttemptDecision("fail")
    if stage == "process" and code in {"FFMPEG_FAILED", "PROCESS_FAILED"}:
        return AttemptDecision("fail")
    if code in TERMINAL_CODES:
        if code == "LOGIN_REQUIRED" and can_use_cookies:
            return AttemptDecision("use_cookies")
        if code == "PROXY_AUTH" and has_next_route and route_switches < max_route_switches:
            return AttemptDecision("switch_route", cool_seconds=3600)
        return AttemptDecision("fail", cool_seconds=3600 if code == "PROXY_AUTH" else 0)

    if code == "RATE_LIMITED":
        if waits_used >= max_waits:
            return AttemptDecision("fail")
        return AttemptDecision("wait", delay=backoff_delay(waits_used, retry_after))

    if code == "BOT_CHECK":
        if can_use_cookies:
            return AttemptDecision("use_cookies")
        if has_next_client:
            return AttemptDecision("retry_client")
        if has_next_route and route_switches < max_route_switches:
            return AttemptDecision("switch_route", cool_seconds=600)
        return AttemptDecision("fail", cool_seconds=600)

    if code == "STREAM_EXPIRED":
        return AttemptDecision("reextract")

    if code in SWITCH_ROUTE_CODES and has_next_route and route_switches < max_route_switches:
        return AttemptDecision("switch_route", cool_seconds=180)

    if code in RETRY_CLIENT_CODES and has_next_client:
        return AttemptDecision("retry_client")

    if code in RETRY_NETWORK_CODES:
        return AttemptDecision("retry_same", delay=1.5)

    if code in {"UNKNOWN", "EXTRACT_FAILED"} and has_next_client:
        return AttemptDecision("retry_client")

    return AttemptDecision("fail")
