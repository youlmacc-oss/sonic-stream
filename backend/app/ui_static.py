from __future__ import annotations

import os
from pathlib import Path


def resolve_ui_dir(start: Path | None = None) -> Path | None:
    raw = (os.getenv("SONICSTREAM_UI_DIR") or "").strip()
    candidates: list[Path] = []
    if raw:
        candidates.append(Path(raw))
    base = start or Path(__file__).resolve()
    backend_root = base.parents[1]
    repo_root = base.parents[2] if len(base.parents) > 2 else backend_root.parent
    candidates.extend(
        [
            repo_root / "frontend" / "out",
            backend_root / "ui",
            backend_root.parent / "ui",
        ]
    )
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "index.html").is_file():
            return resolved
    return None


def ui_html_page(name: str) -> Path | None:
    """Prefer name.html over a same-named folder (Next static export creates both)."""
    ui = resolve_ui_dir()
    if ui is None:
        return None
    safe = Path(name).name
    if not safe or safe in {".", ".."} or safe != name:
        return None
    page = ui / f"{safe}.html"
    if page.is_file():
        return page
    nested = ui / safe / "index.html"
    if nested.is_file():
        return nested
    return None
