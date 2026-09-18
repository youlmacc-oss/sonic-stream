from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from app.env_file import upsert_env_value
from app.local_runtime import ManagedFileError

WINDOW_PAD = 16
WINDOW_CHROME_H = 48
TASKBAR_FALLBACK = 48
MAIN_WINDOW_W = 1280
MAIN_WINDOW_H = 800

BLOCKED_SAVE_ROOTS = (
    Path(os.environ.get("WINDIR", r"C:\Windows")),
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
)


def settings_path() -> Path:
    raw = (os.getenv("SONICSTREAM_SETTINGS") or "").strip()
    if raw:
        return Path(raw)
    appdata = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(appdata) / "SonicStream" / "settings.json"


def load_settings() -> dict[str, Any]:
    path = settings_path()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def save_settings(update: dict[str, Any]) -> dict[str, Any]:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    current = load_settings()
    current.update(update)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return current


def configured_save_dir() -> Path | None:
    raw = str(load_settings().get("save_dir") or "").strip()
    if not raw:
        return None
    try:
        return Path(raw).expanduser()
    except (OSError, RuntimeError, ValueError):
        return None


def _is_blocked_system_path(resolved: Path) -> bool:
    parts = [part.lower() for part in resolved.parts]
    if "windows" in parts[:2] or "system32" in parts:
        return True
    for root in BLOCKED_SAVE_ROOTS:
        try:
            if root.exists() and resolved.is_relative_to(root.resolve()):
                return True
        except (OSError, RuntimeError, ValueError):
            continue
    return False


def validate_save_dir(requested: str) -> Path:
    raw = (requested or "").strip()
    if not raw or "\x00" in raw:
        raise ManagedFileError("FORBIDDEN", "저장 폴더를 확인할 수 없습니다.")
    try:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            raise ManagedFileError("FORBIDDEN", "폴더 전체 경로를 입력해 주세요.")
        resolved = path.resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise ManagedFileError("FORBIDDEN", "저장 폴더를 확인할 수 없습니다.") from exc
    if _is_blocked_system_path(resolved):
        raise ManagedFileError("FORBIDDEN", "시스템 폴더에는 저장할 수 없습니다.")
    try:
        home = install_home().expanduser().resolve()
        if resolved == home or resolved.is_relative_to(home):
            raise ManagedFileError("FORBIDDEN", "프로그램 설치 폴더에는 영상을 저장할 수 없습니다.")
    except ManagedFileError:
        raise
    except (OSError, RuntimeError, ValueError):
        pass
    try:
        resolved.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ManagedFileError("PROCESS_FAILED", "이 폴더를 만들 수 없습니다.") from exc
    if not resolved.is_dir():
        raise ManagedFileError("FORBIDDEN", "폴더만 지정할 수 있습니다.")
    return resolved


def set_save_dir(requested: str) -> Path:
    path = validate_save_dir(requested)
    save_settings({"save_dir": str(path)})
    return path


def pick_folder_dialog() -> str | None:
    if os.name != "nt":
        return None
    script = (
        "Add-Type -AssemblyName System.Windows.Forms; "
        "$d = New-Object System.Windows.Forms.FolderBrowserDialog; "
        "$d.Description = '영상을 저장할 폴더를 선택하세요'; "
        "$d.ShowNewFolderButton = $true; "
        "if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { "
        "[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding $false; "
        "Write-Output $d.SelectedPath }"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            capture_output=True,
            timeout=300,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    path = (completed.stdout or b"").decode("utf-8", "replace").strip()
    return path or None


def install_home() -> Path:
    raw = (os.getenv("SONICSTREAM_HOME") or "").strip()
    if raw:
        return Path(raw)
    appdata = os.getenv("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    return Path(appdata) / "SonicStream"


def startup_shortcut_path() -> Path:
    appdata = os.getenv("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "SonicStream.lnk"


def autostart_enabled() -> bool:
    return startup_shortcut_path().is_file()


def _ps_quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def set_autostart(on: bool) -> bool:
    link = startup_shortcut_path()
    if not on:
        if link.exists():
            link.unlink()
        save_settings({"autostart": False})
        return False
    target = install_home() / "실행하기.bat"
    if not target.is_file():
        raise ManagedFileError("NOT_FOUND", "설치 폴더의 실행 파일을 찾지 못했습니다.")
    script = (
        "$Wsh = New-Object -ComObject WScript.Shell; "
        f"$s = $Wsh.CreateShortcut({_ps_quote(str(link))}); "
        f"$s.TargetPath = {_ps_quote(str(target))}; "
        f"$s.WorkingDirectory = {_ps_quote(str(target.parent))}; "
        "$s.WindowStyle = 7; "
        "$s.Description = 'SonicStream'; "
        "$s.Save()"
    )
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, timeout=20, capture_output=True)
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        raise ManagedFileError("PROCESS_FAILED", "시작 프로그램에 등록하지 못했습니다.") from exc
    save_settings({"autostart": True})
    return True


def _safe_loopback_app_url(url: str) -> str:
    from urllib.parse import urlparse

    from app.local_runtime import is_loopback_host

    parsed = urlparse((url or "").strip())
    host = parsed.netloc or parsed.hostname or ""
    if parsed.scheme not in {"http", "https"} or not is_loopback_host(host):
        raise ManagedFileError("FORBIDDEN", "이 주소는 열 수 없습니다.")
    return f"{parsed.scheme}://{host}/"


def _run_powershell_script(script: str) -> subprocess.CompletedProcess:
    handle = tempfile.NamedTemporaryFile("w", suffix=".ps1", delete=False, encoding="utf-8")
    path = handle.name
    try:
        handle.write(script)
        handle.close()
        return subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", path],
            check=False,
            timeout=8,
            capture_output=True,
        )
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def fit_window_in_area(
    area: tuple[int, int, int, int],
    desired_w: int = MAIN_WINDOW_W,
    desired_h: int = MAIN_WINDOW_H,
    *,
    pad: int = WINDOW_PAD,
    chrome_h: int = 0,
    prefer_x: int = 80,
    prefer_y: int = 40,
) -> tuple[int, int, int, int]:
    left, top, width, height = area
    usable_w = max(1, width - pad * 2)
    usable_h = max(1, height - pad * 2 - chrome_h)
    width_px = min(desired_w, usable_w)
    height_px = min(desired_h, usable_h)
    x = left + prefer_x
    y = top + prefer_y
    max_x = left + width - pad - width_px
    max_y = top + height - pad - chrome_h - height_px
    x = min(max(x, left + pad), max(left + pad, max_x))
    y = min(max(y, top + pad), max(top + pad, max_y))
    return x, y, width_px, height_px


def work_area_rect() -> tuple[int, int, int, int]:
    if os.name != "nt":
        return (0, 0, 1920, 1040)
    import ctypes

    class RECT(ctypes.Structure):
        _fields_ = (
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long),
        )

    rect = RECT()
    try:
        ok = ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(rect), 0)
        full_h = int(ctypes.windll.user32.GetSystemMetrics(1))
    except OSError:
        return (0, 0, 1920, 1040)
    if not ok:
        return (0, 0, 1920, 1040)
    width = max(1, int(rect.right - rect.left))
    height = max(1, int(rect.bottom - rect.top))
    if height >= max(1, full_h) - 2:
        height = max(1, height - TASKBAR_FALLBACK)
    return (int(rect.left), int(rect.top), width, height)


def desktop_app_window_box(
    desired_w: int = MAIN_WINDOW_W,
    desired_h: int = MAIN_WINDOW_H,
) -> tuple[int, int, int, int]:
    return fit_window_in_area(work_area_rect(), desired_w, desired_h, chrome_h=WINDOW_CHROME_H)


def open_or_focus_main_window(url: str) -> dict[str, Any]:
    if os.name != "nt":
        raise ManagedFileError("PROCESS_FAILED", "메인 화면 열기는 Windows에서만 사용할 수 있습니다.")
    app_url = _safe_loopback_app_url(url)
    focus = (
        "Add-Type -TypeDefinition @'\n"
        "using System;\n"
        "using System.Text;\n"
        "using System.Runtime.InteropServices;\n"
        "public class SsFocusMain {\n"
        "  public delegate bool EnumProc(IntPtr hWnd, IntPtr lParam);\n"
        "  [DllImport(\"user32.dll\")] public static extern bool EnumWindows(EnumProc cb, IntPtr l);\n"
        "  [DllImport(\"user32.dll\")] public static extern bool IsWindowVisible(IntPtr hWnd);\n"
        "  [DllImport(\"user32.dll\")] public static extern bool IsIconic(IntPtr hWnd);\n"
        "  [DllImport(\"user32.dll\", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder s, int n);\n"
        "  [DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);\n"
        "  [DllImport(\"user32.dll\")] public static extern bool SetForegroundWindow(IntPtr hWnd);\n"
        "  [DllImport(\"user32.dll\")] public static extern bool BringWindowToTop(IntPtr hWnd);\n"
        "  [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();\n"
        "  [DllImport(\"user32.dll\")] public static extern uint GetWindowThreadProcessId(IntPtr hWnd, out uint pid);\n"
        "  [DllImport(\"user32.dll\")] public static extern bool AttachThreadInput(uint a, uint b, bool attach);\n"
        "  [DllImport(\"kernel32.dll\")] public static extern uint GetCurrentThreadId();\n"
        "  [DllImport(\"user32.dll\")] public static extern void keybd_event(byte bVk, byte bScan, uint flags, UIntPtr extra);\n"
        "  [DllImport(\"user32.dll\")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);\n"
        "  public static IntPtr Found = IntPtr.Zero;\n"
        "  static bool IsMainTitle(string t) {\n"
        "    return t == \"SonicStream\" || t.EndsWith(\"| SonicStream\");\n"
        "  }\n"
        "  public static bool OnWindow(IntPtr h, IntPtr l) {\n"
        "    if (!IsWindowVisible(h)) return true;\n"
        "    var sb = new StringBuilder(512);\n"
        "    if (GetWindowText(h, sb, 512) <= 0) return true;\n"
        "    if (!IsMainTitle(sb.ToString())) return true;\n"
        "    Found = h;\n"
        "    return false;\n"
        "  }\n"
        "  public static IntPtr FindMain() {\n"
        "    Found = IntPtr.Zero;\n"
        "    EnumWindows(OnWindow, IntPtr.Zero);\n"
        "    return Found;\n"
        "  }\n"
        "  public static bool ForceFront(IntPtr h) {\n"
        "    if (h == IntPtr.Zero) return false;\n"
        "    ShowWindow(h, IsIconic(h) ? 9 : 5);\n"
        "    uint pid;\n"
        "    IntPtr fg = GetForegroundWindow();\n"
        "    uint fgTid = fg == IntPtr.Zero ? 0 : GetWindowThreadProcessId(fg, out pid);\n"
        "    uint curTid = GetCurrentThreadId();\n"
        "    if (fgTid != 0 && fgTid != curTid) AttachThreadInput(curTid, fgTid, true);\n"
        "    keybd_event(0x12, 0, 0, UIntPtr.Zero);\n"
        "    keybd_event(0x12, 0, 2, UIntPtr.Zero);\n"
        "    BringWindowToTop(h);\n"
        "    SetForegroundWindow(h);\n"
        "    SetWindowPos(h, new IntPtr(-1), 0, 0, 0, 0, 3);\n"
        "    SetWindowPos(h, new IntPtr(-2), 0, 0, 0, 0, 3);\n"
        "    SetForegroundWindow(h);\n"
        "    if (fgTid != 0 && fgTid != curTid) AttachThreadInput(curTid, fgTid, false);\n"
        "    return true;\n"
        "  }\n"
        "}\n"
        "'@\n"
        "$h = [SsFocusMain]::FindMain()\n"
        "if ($h -ne [IntPtr]::Zero) {\n"
        "  [SsFocusMain]::ForceFront($h) | Out-Null\n"
        "  Write-Output 'focused'\n"
        "  exit 0\n"
        "}\n"
    )
    try:
        found = _run_powershell_script(focus)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ManagedFileError("PROCESS_FAILED", "메인 화면을 열지 못했습니다.") from exc
    if b"focused" in (found.stdout or b""):
        return {"ok": True, "action": "open_main", "opened": "focus"}
    browsers = [
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    ]
    for exe in browsers:
        if not exe.is_file():
            continue
        try:
            x, y, width, height = desktop_app_window_box()
            subprocess.Popen(
                [
                    str(exe),
                    f"--app={app_url}",
                    f"--window-size={width},{height}",
                    f"--window-position={x},{y}",
                ],
                close_fds=True,
            )
            return {"ok": True, "action": "open_main", "opened": "app"}
        except OSError:
            continue
    try:
        os.startfile(app_url)  # type: ignore[attr-defined]
    except OSError as exc:
        raise ManagedFileError("PROCESS_FAILED", "메인 화면을 열지 못했습니다.") from exc
    return {"ok": True, "action": "open_main", "opened": "browser"}


def set_foreground_window_state(action: str) -> dict[str, Any]:
    if os.name != "nt":
        raise ManagedFileError("PROCESS_FAILED", "창 조절은 Windows에서만 사용할 수 있습니다.")
    if action not in {"minimize", "maximize", "restore"}:
        raise ManagedFileError("FORBIDDEN", "창 동작을 확인하지 못했습니다.")
    restore = ""
    if action == "restore":
        x, y, width, height = fit_window_in_area(work_area_rect())
        restore = (
            f"[SsFg]::SetWindowPos($h, [IntPtr]::Zero, {x}, {y}, {width}, {height}, 0x0040) | Out-Null\n"
        )
    show = {"minimize": 6, "maximize": 3, "restore": 9}[action]
    script = (
        "Add-Type -TypeDefinition @'\n"
        "using System;\n"
        "using System.Runtime.InteropServices;\n"
        "public class SsFg {\n"
        "  [DllImport(\"user32.dll\")] public static extern IntPtr GetForegroundWindow();\n"
        "  [DllImport(\"user32.dll\")] public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);\n"
        "  [DllImport(\"user32.dll\")] public static extern bool SetWindowPos(IntPtr hWnd, IntPtr after, int x, int y, int cx, int cy, uint flags);\n"
        "}\n"
        "'@\n"
        "$h = [SsFg]::GetForegroundWindow()\n"
        "if ($h -eq [IntPtr]::Zero) { throw 'NO_WINDOW' }\n"
        f"[SsFg]::ShowWindow($h, {show}) | Out-Null\n"
        f"{restore}"
    )
    try:
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-Command", script],
            check=True,
            timeout=8,
            capture_output=True,
        )
    except (OSError, subprocess.SubprocessError, subprocess.TimeoutExpired) as exc:
        raise ManagedFileError("PROCESS_FAILED", "창 상태를 바꾸지 못했습니다.") from exc
    if completed.returncode != 0:
        raise ManagedFileError("PROCESS_FAILED", "창 상태를 바꾸지 못했습니다.")
    return {"ok": True, "action": action}


def set_openai_api_key(raw: str) -> None:
    key = (raw or "").strip()
    if not key or "\n" in key or "\x00" in key or len(key) > 256:
        raise ManagedFileError("FORBIDDEN", "API 키를 확인하지 못했습니다.")
    upsert_env_value("OPENAI_API_KEY", key)
    os.environ["OPENAI_API_KEY"] = key
    from app.ai_search import verify_openai_key

    verify_openai_key(key)


def desktop_status() -> dict[str, Any]:
    return {
        "save_dir": str(configured_save_dir() or ""),
        "autostart": autostart_enabled(),
        "home": str(install_home()),
    }
