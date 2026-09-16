from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("YOUTUBE_ALLOW_DIRECT", "true")

from app.bundle import build_bundle
from app.classify import classify_error, exception_chain_text, parse_retry_after
from app.diagnostics import extract_http_status
from app.env_snapshot import capture_snapshot, load_snapshot
from app.eventlog import emit_event
from app.log_backup import LogBackup
from app.log_store import reset_store
from app.policy import decide_next
from app.quality import format_display_size, format_fits_quality, pick_video_format, select_download_format
from app.routes import configured_routes
from app.runtime import enabled_js_runtimes
from app.ytdlp_engine import JobYDLLogger, download_client_attempts
from app.youtube_auth import apply_youtube_auth, cookie_state, resolve_cookiefile


class OpsFixTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        os.environ["SONIC_LOG_DIR"] = str(self.dir)
        os.environ["LOG_ROTATE_MAX_BYTES"] = "5000000"
        os.environ["LOG_MAX_TOTAL_BYTES"] = "50000000"
        self.store = reset_store(self.dir)

    def tearDown(self) -> None:
        self.store.stop(timeout=1)
        self.tmp.cleanup()

    def test_user_message_does_not_replace_cause(self) -> None:
        cause = RuntimeError("HTTP Error 403: Forbidden fragment from googlevideo")
        emit_event(
            event="failed",
            stage="download",
            job_id="job-raw",
            error_code="STREAM_FORBIDDEN",
            user_message="미디어 서버가 재생 주소를 거부했습니다.",
            exc=cause,
            origin="external",
        )
        self.store.flush()
        records, _ = self.store.read_records(job_id="job-raw")
        self.assertIn("HTTP Error 403", records[0]["error_message"])
        self.assertEqual(records[0]["user_message"], "미디어 서버가 재생 주소를 거부했습니다.")
        self.assertEqual(records[0]["http_status"], 403)

    def test_http_status_not_guessed_from_quality_number(self) -> None:
        self.assertIsNone(extract_http_status("1080p format 251 selected"))
        self.assertEqual(extract_http_status("HTTP Error 429: Too Many Requests"), 429)

    def test_warning_logger_binds_job(self) -> None:
        JobYDLLogger("job-warn", 2).warning("PO Token provider failed for mweb")
        self.store.flush()
        records, _ = self.store.read_records(job_id="job-warn")
        self.assertTrue(any(item.get("event") == "warning" and "PO Token" in (item.get("error_message") or "") for item in records))
        self.assertEqual(records[0]["attempt_number"], 2)

    def test_exception_cause_preserved_and_masked(self) -> None:
        inner = RuntimeError("cookie=SECRET proxy=http://user:pass@host")
        outer = RuntimeError("extract failed")
        outer.__cause__ = inner
        text = exception_chain_text(outer)
        self.assertIn("extract failed", text)
        self.assertIn("cookie=SECRET", text)
        emit_event(event="failed", stage="extract", job_id="job-cause", exc=outer, origin="external")
        self.store.flush()
        blob = str(self.store.read_records(job_id="job-cause")[0])
        self.assertNotIn("SECRET", blob)
        self.assertNotIn("user:pass", blob)

    def test_bundle_event_count_matches_timeline(self) -> None:
        for i in range(60):
            emit_event(event="started", stage="download", job_id="job-60", attempt_number=i, origin="internal")
        self.store.flush()
        bundle = build_bundle(job_id="job-60")
        self.assertEqual(bundle["manifest"]["event_count"], 60)
        self.assertEqual(len(bundle["timeline"]), 60)
        self.assertEqual(bundle["manifest"]["event_count"], len(bundle["timeline"]))

    def test_snapshot_survives_restart(self) -> None:
        first = capture_snapshot()
        loaded = load_snapshot(first["snapshot_id"])
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded["deploy_version"], first["deploy_version"])
        self.assertEqual(loaded["yt_dlp"], first["yt_dlp"])

    def test_small_current_log_is_backed_up(self) -> None:
        emit_event(event="failed", stage="extract", job_id="job-tiny", error_code="BOT_CHECK", origin="external")
        self.store.flush()
        backup_dir = self.dir / "backup"
        with patch.dict(os.environ, {"LOG_BACKUP_DIR": str(backup_dir)}):
            backup = LogBackup(self.store)
            backup.enqueue_archives()
            self.assertGreaterEqual(backup.process_pending(), 1)
            self.assertTrue(list(backup_dir.rglob("events.jsonl")) or list(backup_dir.rglob("*.jsonl")))

    def test_direct_not_added_when_disallowed(self) -> None:
        with patch.dict(os.environ, {"YOUTUBE_ALLOW_DIRECT": "false", "YOUTUBE_PROXY": "", "YOUTUBE_ROUTES": ""}, clear=False):
            self.assertEqual(configured_routes(), [])

    def test_all_routes_cooled_do_not_fallback(self) -> None:
        decision = decide_next(
            "BOT_CHECK",
            stage="extract",
            attempts=2,
            max_attempts=6,
            waits_used=0,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=False,
            has_next_route=False,
            can_use_cookies=False,
        )
        self.assertEqual(decision.action, "fail")

    def test_retry_after_600_is_not_capped(self) -> None:
        self.assertEqual(parse_retry_after("Retry-After: 600"), 600.0)
        wait = decide_next(
            "RATE_LIMITED",
            stage="extract",
            attempts=1,
            max_attempts=6,
            waits_used=0,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=False,
            has_next_route=False,
            can_use_cookies=False,
            retry_after=600,
            remaining_seconds=700,
        )
        self.assertEqual(wait.action, "wait")
        self.assertEqual(wait.delay, 600)
        expired = decide_next(
            "RATE_LIMITED",
            stage="extract",
            attempts=1,
            max_attempts=6,
            waits_used=0,
            max_waits=2,
            route_switches=0,
            max_route_switches=1,
            has_next_client=False,
            has_next_route=False,
            can_use_cookies=False,
            retry_after=600,
            remaining_seconds=30,
        )
        self.assertEqual(expired.action, "fail")

    def test_format_unavailable_not_unsupported_url(self) -> None:
        missing = classify_error(RuntimeError("Requested format is not available"))
        unsupported = classify_error(RuntimeError("Unsupported URL"))
        self.assertEqual(missing.code, "FORMAT_UNAVAILABLE")
        self.assertEqual(unsupported.code, "UNSUPPORTED_URL")
        retry = decide_next(
            "FORMAT_UNAVAILABLE",
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

    def test_generic_403_is_not_stream_forbidden(self) -> None:
        extract = classify_error(RuntimeError("HTTP Error 403: Forbidden"), stage="extract")
        download = classify_error(RuntimeError("HTTP Error 403: Forbidden fragment from googlevideo"), stage="download")
        self.assertNotEqual(extract.code, "STREAM_FORBIDDEN")
        self.assertEqual(download.code, "STREAM_FORBIDDEN")
        self.assertEqual(
            classify_error(RuntimeError("HTTP Error 403: Forbidden"), stage="download").code,
            "STREAM_FORBIDDEN",
        )

    def test_portrait_and_landscape_same_quality(self) -> None:
        portrait = {"format_id": "p", "width": 720, "height": 1280, "vcodec": "avc1", "tbr": 800}
        landscape = {"format_id": "l", "width": 1280, "height": 720, "vcodec": "avc1", "tbr": 800}
        tall1080 = {"format_id": "t", "width": 1080, "height": 1920, "vcodec": "av01", "tbr": 1200}
        self.assertTrue(format_fits_quality(portrait, "1080p"))
        self.assertTrue(format_fits_quality(landscape, "1080p"))
        self.assertTrue(format_fits_quality(tall1080, "1080p"))
        chosen = pick_video_format([portrait, landscape, tall1080], "1080p")
        self.assertEqual(chosen["format_id"], "t")

    def test_actual_selector_prefers_720x1280_over_608x1080(self) -> None:
        formats = [
            {"format_id": "608", "width": 608, "height": 1080, "vcodec": "avc1", "acodec": "none", "tbr": 900},
            {"format_id": "720", "width": 720, "height": 1280, "vcodec": "avc1", "acodec": "none", "tbr": 1100},
            {"format_id": "audio", "vcodec": "none", "acodec": "mp4a", "tbr": 128},
        ]
        chosen, spec = select_download_format(formats, "1080p")
        self.assertIsNotNone(chosen)
        self.assertEqual(chosen["format_id"], "720")
        self.assertTrue(spec.startswith("720+bestaudio"))

    def test_landscape_1080p_and_square_and_rotation(self) -> None:
        landscape = {"format_id": "l", "width": 1920, "height": 1080, "vcodec": "avc1", "acodec": "none", "tbr": 2000}
        square = {"format_id": "s", "width": 1080, "height": 1080, "vcodec": "avc1", "acodec": "none", "tbr": 1200}
        rotated = {"format_id": "r", "width": 1280, "height": 720, "rotation": 90, "vcodec": "avc1", "acodec": "none", "tbr": 900}
        self.assertEqual(format_display_size(rotated), (720, 1280))
        self.assertEqual(pick_video_format([landscape, square], "1080p")["format_id"], "l")
        chosen_rot = pick_video_format([rotated, {"format_id": "608", "width": 608, "height": 1080, "vcodec": "avc1", "tbr": 800}], "1080p")
        self.assertEqual(chosen_rot["format_id"], "r")
        low = {"format_id": "480", "width": 480, "height": 854, "vcodec": "avc1", "acodec": "aac", "tbr": 400}
        self.assertEqual(pick_video_format([low], "1080p")["format_id"], "480")
        audio_only = [{"format_id": "a", "vcodec": "none", "acodec": "mp4a", "tbr": 128}]
        self.assertIsNone(pick_video_format(audio_only, "1080p"))

    def test_cookie_free_clients_include_tv_and_android(self) -> None:
        attempts = download_client_attempts(use_cookies=False, pot_ok=False)
        self.assertIn(["tv"], attempts)
        self.assertIn(["android"], attempts)
        self.assertIn(["mweb"], attempts)
        opts = apply_youtube_auth({}, use_cookies=False, use_impersonate=False)
        self.assertNotIn("impersonate", opts)
        self.assertNotIn("cookiefile", opts)

    def test_js_runtime_prefers_node_when_both_exist(self) -> None:
        with patch("app.runtime.js_runtime_status", return_value={"deno": True, "node": True}):
            self.assertEqual(enabled_js_runtimes(), {"node": {}})
        with patch("app.runtime.js_runtime_status", return_value={"deno": True, "node": False}):
            self.assertEqual(enabled_js_runtimes(), {"deno": {}})

    def test_empty_cookie_leftovers_do_not_attach(self) -> None:
        with patch.dict(os.environ, {"YOUTUBE_COOKIES": "*", "YOUTUBE_COOKIES_FILE": ""}, clear=False):
            self.assertEqual(cookie_state(), "missing")
            self.assertIsNone(resolve_cookiefile())
            self.assertNotIn("cookiefile", apply_youtube_auth({}, use_cookies=True))
        leftover = self.dir / "empty-cookies.txt"
        leftover.write_text("not a netscape file\n", encoding="utf-8")
        with patch.dict(os.environ, {"YOUTUBE_COOKIES": "", "YOUTUBE_COOKIES_FILE": str(leftover)}, clear=False):
            self.assertEqual(cookie_state(), "invalid_format")
            self.assertIsNone(resolve_cookiefile())
            self.assertNotIn("cookiefile", apply_youtube_auth({}, use_cookies=True))

    def test_fallback_success_summarized_as_success(self) -> None:
        emit_event(event="failed", stage="extract", job_id="job-fb", error_code="BOT_CHECK", extra={"final": False})
        emit_event(event="succeeded", stage="postprocess", job_id="job-fb")
        self.store.flush()
        bundle = build_bundle(job_id="job-fb")
        self.assertEqual(bundle["summary"]["last_event"], "succeeded")
        self.assertEqual(bundle["summary"]["first_error"]["error_code"], "BOT_CHECK")


if __name__ == "__main__":
    unittest.main()
