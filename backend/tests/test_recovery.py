from __future__ import annotations

import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("YOUTUBE_ALLOW_DIRECT", "true")

from app.classify import classify_error
from app.diagnostics import mask_text
from app.gc import delete_job_dir, job_dir_for, sweep_expired
from app.jobs import store
from app.limiter import DownloadLimiter
from app.models import InspectResponse
from app.policy import decide_next
from app.routes import NetworkRoute, recover_route
from app.sse import snapshot_event
from app.youtube_auth import cookie_state, resolve_cookiefile
from app.ytdlp_engine import inspect_url, run_download, validate_combo
from error_logger import log_error, read_backlog


class RecoveryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        store._jobs.clear()
        recover_route("direct")
        recover_route("proxy")
        recover_route("home")
        self.verify_patch = patch(
            "app.ytdlp_engine.evaluate_saved_media",
            return_value={"ok": True, "code": None, "probe": {"width": 1280, "height": 720}, "file_bytes": 16},
        )
        self.verify_patch.start()
        self.addCleanup(self.verify_patch.stop)

    def test_rate_limit_wait_has_upper_bound(self) -> None:
        first = decide_next(
            "RATE_LIMITED",
            stage="extract",
            attempts=1,
            max_attempts=4,
            waits_used=0,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=True,
            has_next_route=True,
            can_use_cookies=False,
            retry_after=8,
        )
        self.assertEqual(first.action, "wait")
        self.assertEqual(first.delay, 8)
        exhausted = decide_next(
            "RATE_LIMITED",
            stage="extract",
            attempts=3,
            max_attempts=4,
            waits_used=2,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=True,
            has_next_route=True,
            can_use_cookies=False,
        )
        self.assertEqual(exhausted.action, "fail")

    def test_bot_check_differs_from_403_and_login(self) -> None:
        bot = classify_error(RuntimeError("Sign in to confirm you’re not a bot"))
        forbidden = classify_error(RuntimeError("HTTP Error 403: Forbidden fragment from googlevideo"))
        login = classify_error(RuntimeError("login_required: Sign in to your account"))
        self.assertEqual(bot.code, "BOT_CHECK")
        self.assertEqual(forbidden.code, "STREAM_FORBIDDEN")
        self.assertEqual(login.code, "LOGIN_REQUIRED")
        self.assertNotEqual(bot.code, forbidden.code)

    def test_bot_check_retries_client_before_fail(self) -> None:
        retry = decide_next(
            "BOT_CHECK",
            stage="extract",
            attempts=1,
            max_attempts=6,
            waits_used=0,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=True,
            has_next_route=False,
            can_use_cookies=False,
        )
        self.assertEqual(retry.action, "retry_client")
        self.assertEqual(retry.cool_seconds, 0)
        exhausted = decide_next(
            "BOT_CHECK",
            stage="extract",
            attempts=3,
            max_attempts=6,
            waits_used=0,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=False,
            has_next_route=False,
            can_use_cookies=False,
        )
        self.assertEqual(exhausted.action, "fail")
        self.assertEqual(exhausted.cool_seconds, 600)

    def test_bot_check_retries_next_client_and_does_not_cool(self) -> None:
        from app.routes import is_cooled
        from app.ytdlp_engine import run_download

        calls: list[str] = []

        class FakeYDL:
            def __init__(self, opts):
                self.opts = opts
                youtube = (opts.get("extractor_args") or {}).get("youtube") or {}
                self.clients = youtube.get("player_client")

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                label = ",".join(self.clients) if self.clients else "default"
                calls.append(label)
                if self.clients is None:
                    raise RuntimeError("Sign in to confirm you’re not a bot")
                return {"title": "ok", "is_live": False}

            def process_ie_result(self, info, download=True):
                job_dir = Path(self.opts["outtmpl"]).parent
                (job_dir / "ok.mp4").write_bytes(b"data")

        store.create("job-bot", "video", "1080p")
        with patch("app.ytdlp_engine.YoutubeDL", FakeYDL), patch("app.ytdlp_engine.pot_ready", return_value=False):
            run_download("job-bot", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video", "1080p")
        job = store.get("job-bot")
        self.assertEqual(job.status, "done")
        self.assertIn("default", calls)
        self.assertTrue(any(item != "default" for item in calls))
        self.assertFalse(is_cooled("direct"))

    def test_pot_failure_differs_from_js_runtime(self) -> None:
        pot = classify_error(RuntimeError("PO Token provider failed to supply a token"))
        missing = classify_error(RuntimeError("A PO Token is required for this client"))
        js = classify_error(RuntimeError("JavaScript runtime is required to solve EJS challenges"))
        self.assertEqual(pot.code, "POT_FAILED")
        self.assertEqual(missing.code, "POT_MISSING")
        self.assertEqual(js.code, "JS_RUNTIME")

    def test_proxy_auth_connect_and_switch(self) -> None:
        auth = classify_error(RuntimeError("407 Proxy Authentication Required"))
        connect = classify_error(RuntimeError("HTTPS proxy connection refused while opening tunnel"))
        self.assertEqual(auth.code, "PROXY_AUTH")
        self.assertEqual(connect.code, "PROXY_CONNECT")
        auth_decision = decide_next(
            "PROXY_AUTH",
            stage="extract",
            attempts=1,
            max_attempts=4,
            waits_used=0,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=False,
            has_next_route=True,
            can_use_cookies=False,
        )
        self.assertEqual(auth_decision.action, "switch_route")
        no_repeat = decide_next(
            "PROXY_AUTH",
            stage="extract",
            attempts=2,
            max_attempts=4,
            waits_used=0,
            max_waits=2,
            route_switches=1,
            max_route_switches=1,
            has_next_client=False,
            has_next_route=True,
            can_use_cookies=False,
        )
        self.assertEqual(no_repeat.action, "fail")

    def test_route_switch_requires_reextract(self) -> None:
        decision = decide_next(
            "STREAM_FORBIDDEN",
            stage="download",
            attempts=1,
            max_attempts=4,
            waits_used=0,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=False,
            has_next_route=True,
            can_use_cookies=False,
        )
        self.assertEqual(decision.action, "switch_route")
        expired = decide_next(
            "STREAM_EXPIRED",
            stage="download",
            attempts=1,
            max_attempts=4,
            waits_used=0,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=False,
            has_next_route=False,
            can_use_cookies=False,
        )
        self.assertEqual(expired.action, "reextract")

    def test_cookie_lock_and_log_masking(self) -> None:
        netscape = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tLOGIN_INFO\tsecret-value\n"
        with patch.dict(os.environ, {"YOUTUBE_COOKIES": netscape, "YOUTUBE_COOKIES_FILE": ""}, clear=False):
            paths: list[str | None] = []

            def worker() -> None:
                paths.append(resolve_cookiefile())

            threads = [threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertTrue(all(path and Path(path).exists() for path in paths))
            self.assertEqual(cookie_state(), "file_present")

        masked = mask_text("cookie=LOGIN_INFO=abc; https://googlevideo.com/videoplayback?signature=xyz&n=abcdefghijk")
        self.assertNotIn("LOGIN_INFO", masked)
        self.assertNotIn("signature=xyz", masked)
        self.assertIn("[redacted]", masked)

        with tempfile.TemporaryDirectory() as tmp:
            from app.log_store import reset_store

            reset_store(Path(tmp))
            log_error(
                endpoint="/api/download",
                error=RuntimeError("cookie=SECRET traceback would go here"),
                request_data={"job_id": "j1", "proxy": "http://user:pass@host", "url": "https://youtu.be/dQw4w9WgXcQ"},
            )
            from app.log_store import get_store
            get_store().flush()
            items = read_backlog(1)
            self.assertNotIn("proxy", items[0]["request_data"])
            self.assertIn("[redacted]", items[0]["error_message"])
            self.assertNotIn("SECRET", items[0]["error_message"])

    def test_limiter_caps_and_dedupes(self) -> None:
        limiter = DownloadLimiter()
        with patch.dict(os.environ, {"MAX_CONCURRENT_DOWNLOADS": "1", "MAX_DOWNLOAD_QUEUE": "1"}):
            first = limiter.admit("job-a", "u|video|1080p")
            second = limiter.admit("job-b", "u|video|1080p")
            third = limiter.admit("job-c", "other|video|1080p")
            fourth = limiter.admit("job-d", "third|video|1080p")
            self.assertTrue(first.ok)
            self.assertFalse(second.ok)
            self.assertEqual(second.existing_job_id, "job-a")
            self.assertTrue(third.ok)
            self.assertFalse(fourth.ok)
            self.assertEqual(fourth.reason, "busy")
            self.assertEqual(limiter.snapshot()["active"] + limiter.snapshot()["queued"], 2)

    def test_timeout_does_not_overwrite_done(self) -> None:
        job = store.create("job-timeout", "video", "1080p")
        settled = store.settle("job-timeout", "error", error_code="TIMEOUT", error_message="시간이 초과되었습니다.")
        later = store.settle("job-timeout", "done", download_url="/api/fetch/job-timeout")
        self.assertIsNotNone(settled)
        self.assertIsNone(later)
        self.assertEqual(job.status, "error")
        self.assertTrue(job.settled)
        store.update("job-timeout", status="done")
        self.assertEqual(store.get("job-timeout").status, "error")

    def test_gc_skips_active_job_dirs(self) -> None:
        job = store.create("job-active", "video", "1080p")
        job.status = "downloading"
        job.worker_alive = True
        path = job_dir_for("job-active")
        path.mkdir(parents=True, exist_ok=True)
        (path / "partial.mp4.part").write_text("x", encoding="utf-8")
        old = time.time() - 3600
        os.utime(path, (old, old))
        sweep_expired()
        self.assertTrue(path.exists())
        delete_job_dir("job-active")
        self.assertTrue(path.exists())
        job.status = "done"
        job.worker_alive = False
        job.settled = True
        delete_job_dir("job-active")
        self.assertFalse(path.exists())

    def test_sse_queued_retrying_and_terminal_once(self) -> None:
        job = store.create("job-sse", "audio", "320k")
        name, payload = snapshot_event(job)
        self.assertEqual(name, "queued")
        self.assertEqual(payload["status"], "queued")
        store.update("job-sse", status="retrying", detail="요청 제한으로 대기 중...", wait_reason="rate_limit")
        name, payload = snapshot_event(store.get("job-sse"))
        self.assertEqual(name, "retrying")
        self.assertIn("대기", payload["detail"])
        store.settle("job-sse", "error", error_code="RATE_LIMITED", error_message="요청이 많아 잠시 대기한 뒤 다시 시도합니다.")
        name, payload = snapshot_event(store.get("job-sse"))
        self.assertEqual(name, "error")
        overwritten = store.settle("job-sse", "done")
        self.assertIsNone(overwritten)

    def test_oembed_success_is_preview_only(self) -> None:
        preview = InspectResponse(title="Demo", author="A", duration="00:00", thumbnail="x", preview_only=True)
        with patch("app.ytdlp_engine.inspect_via_oembed", return_value=(preview, False)), patch(
            "app.ytdlp_engine.inspect_via_ytdlp"
        ) as ytdlp:
            result = inspect_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ")
            self.assertTrue(result.preview_only)
            self.assertEqual(result.title, "Demo")
            ytdlp.assert_not_called()

    def test_oembed_404_is_not_deleted(self) -> None:
        with patch("app.ytdlp_engine.inspect_via_oembed", return_value=(None, True)), patch(
            "app.ytdlp_engine.inspect_via_ytdlp",
            return_value={"title": "Real", "uploader": "Ch", "duration": 12, "thumbnail": "t"},
        ):
            result = inspect_url("https://youtu.be/abcdefghijk")
            self.assertFalse(result.preview_only)
            self.assertEqual(result.title, "Real")

    def test_download_contract_and_quality_options(self) -> None:
        validate_combo("video", "1080p")
        validate_combo("video", "4k")
        validate_combo("audio", "320k")
        validate_combo("audio", "flac")
        with self.assertRaises(ValueError):
            validate_combo("video", "320k")

    def test_ffmpeg_error_does_not_reextract(self) -> None:
        decision = decide_next(
            "FFMPEG_FAILED",
            stage="process",
            attempts=1,
            max_attempts=4,
            waits_used=0,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=True,
            has_next_route=True,
            can_use_cookies=True,
        )
        self.assertEqual(decision.action, "fail")

    def test_run_download_switches_route_and_reextracts(self) -> None:
        calls: list[tuple[str | None, str | None]] = []

        class FakeYDL:
            def __init__(self, opts):
                self.opts = opts

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                calls.append((self.opts.get("proxy"), "extract"))
                if self.opts.get("proxy") is None:
                    raise RuntimeError("HTTP Error 403: Forbidden fragment from googlevideo")
                return {"title": "ok", "is_live": False}

            def process_ie_result(self, info, download=True):
                calls.append((self.opts.get("proxy"), "download"))
                job_dir = Path(self.opts["outtmpl"]).parent
                (job_dir / "ok.mp4").write_bytes(b"data")

        store.create("job-route", "video", "1080p")
        with patch("app.ytdlp_engine.YoutubeDL", FakeYDL), patch(
            "app.ytdlp_engine.available_routes",
            return_value=[NetworkRoute("direct", None), NetworkRoute("home", "http://proxy.example:8080")],
        ), patch(
            "app.ytdlp_engine.next_route",
            side_effect=lambda current: NetworkRoute("home", "http://proxy.example:8080") if current == "direct" else None,
        ), patch("app.ytdlp_engine.configured_routes", return_value=[NetworkRoute("direct", None), NetworkRoute("home", "http://proxy.example:8080")]):
            run_download("job-route", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video", "1080p")

        job = store.get("job-route")
        self.assertEqual(job.status, "done")
        self.assertIn(("http://proxy.example:8080", "extract"), calls)
        self.assertIn(("http://proxy.example:8080", "download"), calls)
        self.assertTrue(any(proxy is None and stage == "extract" for proxy, stage in calls))

    def test_cancelled_job_does_not_finish(self) -> None:
        class SlowYDL:
            def __init__(self, opts):
                self.opts = opts

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def extract_info(self, url, download=False):
                job = store.get("job-cancel")
                job.cancel_event.set()
                raise RuntimeError("HTTP Error 429: Too Many Requests Retry-After: 30")

            def process_ie_result(self, info, download=True):
                raise AssertionError("should not download after cancel")

        store.create("job-cancel", "video", "1080p")
        with patch("app.ytdlp_engine.YoutubeDL", SlowYDL):
            run_download("job-cancel", "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "video", "1080p")
        job = store.get("job-cancel")
        self.assertEqual(job.status, "error")
        self.assertNotEqual(job.status, "done")


if __name__ == "__main__":
    unittest.main()
