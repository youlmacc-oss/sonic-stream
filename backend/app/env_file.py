from __future__ import annotations

import os
from pathlib import Path

ALLOWED_ENV_KEYS = {"OPENAI_API_KEY", "OPENAI_MODEL"}


def parse_env_line(line: str) -> tuple[str, str] | None:
    text = line.strip()
    if not text or text.startswith("#") or "=" not in text:
        return None
    key, _, raw = text.partition("=")
    name = key.strip()
    if not name:
        return None
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    return name, value


def apply_env_file(path: Path, *, override: bool = False) -> None:
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return
    for line in lines:
        parsed = parse_env_line(line)
        if parsed is None:
            continue
        name, value = parsed
        if not override and name in os.environ:
            continue
        os.environ[name] = value


def load_dotenv_files() -> list[Path]:
    candidates: list[Path] = []
    home = (os.getenv("SONICSTREAM_HOME") or "").strip()
    if home:
        candidates.append(Path(home) / ".env")
    backend_root = Path(__file__).resolve().parents[1]
    candidates.append(backend_root / ".env")
    repo_root = backend_root.parent
    if repo_root != backend_root:
        candidates.append(repo_root / ".env")
    loaded: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        try:
            resolved = path.expanduser().resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_file():
            continue
        seen.add(resolved)
        apply_env_file(resolved)
        loaded.append(resolved)
    return loaded


def writable_env_path() -> Path:
    home = (os.getenv("SONICSTREAM_HOME") or "").strip()
    if home:
        return Path(home) / ".env"
    return Path(__file__).resolve().parents[1] / ".env"


def upsert_env_value(name: str, value: str, path: Path | None = None) -> Path:
    if name not in ALLOWED_ENV_KEYS:
        raise ValueError(name)
    target = path or writable_env_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        lines = []
    next_lines: list[str] = []
    replaced = False
    for line in lines:
        parsed = parse_env_line(line)
        if parsed and parsed[0] == name:
            next_lines.append(f"{name}={value}")
            replaced = True
        else:
            next_lines.append(line)
    if not replaced:
        if next_lines and next_lines[-1].strip():
            next_lines.append("")
        next_lines.append(f"{name}={value}")
    target.write_text("\n".join(next_lines) + "\n", encoding="utf-8")
    os.environ[name] = value
    return target
