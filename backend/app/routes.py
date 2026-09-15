from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class NetworkRoute:
    alias: str
    proxy: str | None


_lock = threading.Lock()
_cool_until: dict[str, float] = {}


def _truthy(name: str, default: str = "true") -> bool:
    return (os.getenv(name, default) or default).strip().lower() not in {"0", "false", "off", "no"}


def configured_routes() -> list[NetworkRoute]:
    routes: list[NetworkRoute] = []
    if _truthy("YOUTUBE_ALLOW_DIRECT", "true"):
        routes.append(NetworkRoute("direct", None))

    named = [item.strip() for item in (os.getenv("YOUTUBE_ROUTES") or "").split(",") if item.strip()]
    for alias in named:
        proxy = (os.getenv(f"YOUTUBE_ROUTE_{alias}") or os.getenv(f"YOUTUBE_ROUTE_{alias.upper()}") or "").strip()
        if proxy:
            routes.append(NetworkRoute(alias, proxy))

    legacy = (os.getenv("YOUTUBE_PROXY") or "").strip()
    if legacy and not any(route.alias == "proxy" for route in routes):
        routes.append(NetworkRoute("proxy", legacy))

    if not routes:
        routes.append(NetworkRoute("direct", None))
    return routes


def is_cooled(alias: str) -> bool:
    with _lock:
        until = _cool_until.get(alias, 0.0)
        return until > time.time()


def cool_route(alias: str, seconds: float) -> None:
    with _lock:
        _cool_until[alias] = max(_cool_until.get(alias, 0.0), time.time() + max(1.0, seconds))


def recover_route(alias: str) -> None:
    with _lock:
        _cool_until.pop(alias, None)


def available_routes() -> list[NetworkRoute]:
    return [route for route in configured_routes() if not is_cooled(route.alias)]


def next_route(current: str | None) -> NetworkRoute | None:
    routes = available_routes()
    if not routes:
        return None
    if current is None:
        return routes[0]
    aliases = [route.alias for route in routes]
    if current not in aliases:
        return routes[0]
    index = aliases.index(current)
    if index + 1 >= len(routes):
        return None
    return routes[index + 1]


def route_status() -> list[dict[str, object]]:
    now = time.time()
    with _lock:
        cooled = dict(_cool_until)
    return [
        {
            "alias": route.alias,
            "has_proxy": route.proxy is not None,
            "cooled": is_cooled(route.alias),
            "cool_remaining": max(0, int((cooled.get(route.alias, 0) - now))),
        }
        for route in configured_routes()
    ]
