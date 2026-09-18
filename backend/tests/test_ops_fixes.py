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
from app.desktop import fit_window_in_area, set_foreground_window_state, set_save_dir, settings_path, validate_save_dir
from app.installer import installer_file, installer_public_url, setup_batch
from app.local_runtime import ManagedFileError, default_save_dir, resolve_managed_file, runtime_location
from app.env_file import apply_env_file, parse_env_line, upsert_env_value
from app.ui_static import resolve_ui_dir, ui_html_page
from app.ytdlp_engine import (
    JobYDLLogger,
    download_client_attempts,
    format_view_count,
    normalize_search_query,
    reset_ffmpeg_dir_cache,
    resolve_ffmpeg_dir,
    SEARCH_RESULT_MAX,
    innertube_continuation_token,
    search_hits_from_info,
    search_hits_from_innertube,
    search_videos,
)
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

    def test_managed_file_stays_inside_save_dir(self) -> None:
        save = self.dir / "SonicStream"
        save.mkdir()
        safe = save / "漂亮的藏族姑娘 (1).mp4"
        safe.write_bytes(b"abc")
        outside = self.dir / "secret.txt"
        outside.write_text("no", encoding="utf-8")
        with patch("app.local_runtime.default_save_dir", return_value=save):
            resolved = resolve_managed_file(str(safe))
            self.assertEqual(resolved, safe.resolve())
            self.assertEqual(resolve_managed_file(safe.name), safe.resolve())
            with self.assertRaises(ManagedFileError) as denied:
                resolve_managed_file(str(outside))
            self.assertEqual(denied.exception.code, "FORBIDDEN")
            with self.assertRaises(ManagedFileError) as missing:
                resolve_managed_file(str(save / "gone.mp4"))
            self.assertEqual(missing.exception.code, "NOT_FOUND")
            with self.assertRaises(ManagedFileError):
                resolve_managed_file(str(save / ".." / "secret.txt"))

    def test_env_file_parses_and_does_not_override(self) -> None:
        self.assertEqual(parse_env_line("OPENAI_API_KEY=sk-test"), ("OPENAI_API_KEY", "sk-test"))
        self.assertEqual(parse_env_line('OPENAI_MODEL="gpt-4o-mini"'), ("OPENAI_MODEL", "gpt-4o-mini"))
        self.assertIsNone(parse_env_line("# comment"))
        path = self.dir / ".env"
        path.write_text("OPENAI_MODEL=from-file\n", encoding="utf-8")
        with patch.dict(os.environ, {"OPENAI_MODEL": "already-set"}, clear=False):
            apply_env_file(path)
            self.assertEqual(os.environ["OPENAI_MODEL"], "already-set")
            apply_env_file(path, override=True)
            self.assertEqual(os.environ["OPENAI_MODEL"], "from-file")
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            upsert_env_value("OPENAI_API_KEY", "sk-user", path)
            self.assertIn("OPENAI_API_KEY=sk-user", path.read_text(encoding="utf-8"))
            self.assertEqual(os.environ["OPENAI_API_KEY"], "sk-user")
            upsert_env_value("OPENAI_API_KEY", "sk-next", path)
            self.assertEqual(path.read_text(encoding="utf-8").count("OPENAI_API_KEY="), 1)
            self.assertIn("OPENAI_API_KEY=sk-next", path.read_text(encoding="utf-8"))

    def test_ui_dir_uses_index_and_env(self) -> None:
        missing = self.dir / "empty-ui"
        missing.mkdir()
        with patch.dict(os.environ, {"SONICSTREAM_UI_DIR": ""}, clear=False):
            self.assertIsNone(resolve_ui_dir(start=missing / "app" / "ui_static.py"))
        ui = self.dir / "packaged-ui"
        ui.mkdir()
        (ui / "index.html").write_text("<html><title>SonicStream</title></html>", encoding="utf-8")
        with patch.dict(os.environ, {"SONICSTREAM_UI_DIR": str(ui)}, clear=False):
            self.assertEqual(resolve_ui_dir(), ui.resolve())
            (ui / "search.html").write_text("<html>search</html>", encoding="utf-8")
            (ui / "search").mkdir()
            (ui / "search" / "payload.txt").write_text("x", encoding="utf-8")
            self.assertEqual(ui_html_page("search"), (ui / "search.html").resolve())
            (ui / "help.html").write_text("<html>help</html>", encoding="utf-8")
            (ui / "help").mkdir()
            self.assertEqual(ui_html_page("help"), (ui / "help.html").resolve())
            self.assertIsNone(ui_html_page("../secret"))

    def test_ffmpeg_dir_prefers_env_over_cache(self) -> None:
        bundled = self.dir / "ffmpeg"
        bundled.mkdir()
        exe = bundled / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        exe.write_bytes(b"")
        reset_ffmpeg_dir_cache()
        with patch.dict(os.environ, {"SONICSTREAM_FFMPEG_DIR": str(bundled)}, clear=False):
            self.assertEqual(resolve_ffmpeg_dir(), bundled.resolve())
        reset_ffmpeg_dir_cache()

    def test_save_dir_settings_and_system_folder_blocked(self) -> None:
        cfg = self.dir / "settings.json"
        chosen = self.dir / "Videos"
        with patch.dict(os.environ, {"SONICSTREAM_SETTINGS": str(cfg)}, clear=False):
            saved = set_save_dir(str(chosen))
            self.assertEqual(saved, chosen.resolve())
            self.assertEqual(default_save_dir().resolve(), chosen.resolve())
            self.assertEqual(settings_path(), cfg)
            with self.assertRaises(ManagedFileError) as blocked:
                validate_save_dir(r"C:\Windows")
            self.assertEqual(blocked.exception.code, "FORBIDDEN")
            with self.assertRaises(ManagedFileError):
                validate_save_dir("relative-folder")
        with self.assertRaises(ManagedFileError) as window_denied:
            set_foreground_window_state("explode")
        self.assertEqual(window_denied.exception.code, "FORBIDDEN")
        self.assertEqual(fit_window_in_area((0, 0, 1920, 1040), 1280, 800), (80, 40, 1280, 800))
        small = fit_window_in_area((0, 0, 1280, 720), 1280, 840)
        self.assertEqual(small[2], 1248)
        self.assertEqual(small[3], 688)
        self.assertGreaterEqual(small[1], 16)
        self.assertLessEqual(small[1] + small[3], 720 - 16)
        from app.desktop import _safe_loopback_app_url

        self.assertEqual(_safe_loopback_app_url("http://127.0.0.1:8011/ai"), "http://127.0.0.1:8011/")
        with self.assertRaises(ManagedFileError) as remote_denied:
            _safe_loopback_app_url("https://example.com/")
        self.assertEqual(remote_denied.exception.code, "FORBIDDEN")

    def test_search_hits_map_watch_urls(self) -> None:
        self.assertEqual(normalize_search_query("  봄비  노래  "), "봄비 노래")
        self.assertEqual(format_view_count(1234567), "123만회")
        self.assertEqual(format_view_count("조회수 8.5천회"), "8.5천회")
        self.assertEqual(format_view_count("1.2M views"), "120만회")
        with self.assertRaises(ValueError):
            normalize_search_query("")
        hits = search_hits_from_info(
            {
                "entries": [
                    {"id": "kSahhqze9Ss", "title": "Shorts", "uploader": "Ch", "duration": 13, "view_count": 1234567, "thumbnail": "https://i.ytimg.com/vi/kSahhqze9Ss/hqdefault.jpg"},
                    {"id": "skip", "url": "not-a-url"},
                ]
            }
        )
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["url"], "https://www.youtube.com/watch?v=kSahhqze9Ss")
        self.assertEqual(hits[0]["title"], "Shorts")
        self.assertTrue(hits[0]["duration_known"])
        self.assertEqual(hits[0]["views"], "123만회")
        tube = search_hits_from_innertube(
            {
                "contents": {
                    "twoColumnSearchResultsRenderer": {
                        "primaryContents": {
                            "sectionListRenderer": {
                                "contents": [
                                    {
                                        "itemSectionRenderer": {
                                            "contents": [
                                                {
                                                    "lockupViewModel": {
                                                        "contentId": "RDPLAYLIST01",
                                                        "metadata": {"lockupMetadataViewModel": {"title": {"content": "재생목록"}}},
                                                    }
                                                },
                                                {
                                                    "videoRenderer": {
                                                        "videoId": "lRaJ86Pe52o",
                                                        "title": {"runs": [{"text": "전유진 - 나의 별들에게"}]},
                                                        "ownerText": {"runs": [{"text": "1theK"}]},
                                                        "lengthText": {"simpleText": "3:46"},
                                                        "shortViewCountText": {"simpleText": "123만회"},
                                                        "thumbnail": {"thumbnails": [{"url": "https://i.ytimg.com/vi/lRaJ86Pe52o/hqdefault.jpg"}]},
                                                    }
                                                },
                                            ]
                                        }
                                    }
                                ]
                            }
                        }
                    }
                }
            }
        )
        self.assertEqual(len(tube), 1)
        self.assertEqual(tube[0]["url"], "https://www.youtube.com/watch?v=lRaJ86Pe52o")
        self.assertEqual(tube[0]["title"], "전유진 - 나의 별들에게")
        self.assertEqual(tube[0]["author"], "1theK")
        self.assertEqual(tube[0]["duration"], "3:46")
        self.assertEqual(tube[0]["views"], "123만회")
        token = innertube_continuation_token(
            {
                "contents": {
                    "continuationItemRenderer": {
                        "continuationEndpoint": {"continuationCommand": {"token": "NEXT30"}}
                    }
                }
            }
        )
        self.assertEqual(token, "NEXT30")
        many = [{"title": f"v{i}", "author": "a", "url": f"https://www.youtube.com/watch?v={i:011d}", "thumbnail": "", "duration": "", "duration_known": False} for i in range(40)]
        with patch("app.ytdlp_engine.search_via_innertube", return_value=many), patch("app.ytdlp_engine._search_cache_get", return_value=None):
            result = search_videos("전유진", 40)
        self.assertEqual(len(result["items"]), SEARCH_RESULT_MAX)

    def test_transcript_parses_captions(self) -> None:
        from app.transcript import parse_json3_captions, parse_vtt_captions, pick_caption_track

        json_lines = parse_json3_captions(
            '{"events":[{"tStartMs":1200,"segs":[{"utf8":"안녕 "},{"utf8":"하세요"}]},{"tStartMs":4000,"segs":[{"utf8":"\\n"}]}]}'
        )
        self.assertEqual(json_lines[0]["text"], "안녕 하세요")
        self.assertEqual(json_lines[0]["start"], 1.2)
        vtt_lines = parse_vtt_captions(
            "WEBVTT\n\n00:00:01.000 --> 00:00:03.000\n첫 줄\n\n00:01:02.500 --> 00:01:05.000\n둘째 줄"
        )
        self.assertEqual([item["text"] for item in vtt_lines], ["첫 줄", "둘째 줄"])
        self.assertEqual(vtt_lines[1]["start"], 62.5)
        picked = pick_caption_track(
            {
                "automatic_captions": {
                    "en": [{"ext": "vtt", "url": "https://example.com/en.vtt"}],
                    "ko": [{"ext": "json3", "url": "https://example.com/ko.json3"}],
                }
            }
        )
        self.assertIsNotNone(picked)
        lang, automatic, track = picked or ("", False, {})
        self.assertEqual(lang, "ko")
        self.assertTrue(automatic)
        self.assertEqual(track["ext"], "json3")

    def test_ai_search_plans_keywords_and_hits(self) -> None:
        from app.ai_search import AiSearchError, _parse_plan, collect_ytsearch_hits, plan_search, run_ai_search

        reply, keywords = _parse_plan(
            '{"reply":"전유진 무대를 찾아볼게요.","keywords":["전유진 현역가왕","전유진 히든싱어"]}',
            "비 오는 날 전유진",
        )
        self.assertEqual(reply, "전유진 무대를 찾아볼게요.")
        self.assertEqual(keywords, ["전유진 현역가왕", "전유진 히든싱어"])
        with patch("app.ai_search.search_ytsearch", return_value=[
            {"title": "A", "author": "Ch", "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "thumbnail": "t", "duration": "03:00", "duration_known": True},
            {"title": "B", "author": "Ch", "url": "https://www.youtube.com/watch?v=bbbbbbbbbbb", "thumbnail": "t", "duration": "04:00", "duration_known": True},
            {"title": "C", "author": "Ch", "url": "https://www.youtube.com/watch?v=ccccccccccc", "thumbnail": "t", "duration": "05:00", "duration_known": True},
        ]) as mocked:
            hits = collect_ytsearch_hits(["전유진 현역가왕", "전유진 히든싱어"], 3)
            self.assertEqual(len(hits), 3)
            self.assertEqual(mocked.call_count, 1)
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            with self.assertRaises(AiSearchError) as missing:
                plan_search("전유진 노래")
            self.assertEqual(missing.exception.code, "AI_UNAVAILABLE")
        with patch("app.ai_search.plan_search", return_value=("추천합니다.", ["전유진"])), patch(
            "app.ai_search.collect_ytsearch_hits",
            return_value=[{"title": "A", "author": "Ch", "url": "https://www.youtube.com/watch?v=aaaaaaaaaaa", "thumbnail": "", "duration": "1:00", "duration_known": True}],
        ):
            result = run_ai_search("  전유진 좋은 무대  ")
        self.assertEqual(result["keywords"], ["전유진"])
        self.assertEqual(len(result["items"]), 1)
        from app.ai_search import connection_status
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}, clear=False):
            status = connection_status()
        self.assertEqual(status["engine"], "ok")
        self.assertEqual(status["openai"], "no_key")

    def test_installer_info_uses_file_or_public_url(self) -> None:
        zip_path = self.dir / "SonicStream-Windows.zip"
        zip_path.write_bytes(b"zip")
        with patch.dict(os.environ, {"SONICSTREAM_INSTALLER_PATH": str(zip_path), "SONICSTREAM_INSTALLER_URL": ""}, clear=False):
            self.assertEqual(installer_file(), zip_path.resolve())
            self.assertTrue(installer_public_url("http://127.0.0.1:8000/").endswith("/api/desktop/installer"))
        with patch.dict(os.environ, {"SONICSTREAM_INSTALLER_PATH": "", "SONICSTREAM_INSTALLER_URL": "https://example.com/app.zip"}, clear=False):
            self.assertEqual(installer_public_url(), "https://example.com/app.zip")
        bat = setup_batch("https://example.com/app.zip")
        self.assertIn("https://example.com/app.zip", bat)
        self.assertIn("install-desktop.ps1", bat)

    def test_packaged_ui_defaults_to_local(self) -> None:
        with patch.dict(os.environ, {"SONICSTREAM_LOCATION": "", "SONICSTREAM_UI_DIR": str(self.dir)}, clear=False):
            self.assertEqual(runtime_location(), "local")
        with patch.dict(os.environ, {"SONICSTREAM_LOCATION": "server", "SONICSTREAM_UI_DIR": str(self.dir)}, clear=False):
            self.assertEqual(runtime_location(), "server")

    def test_fallback_success_summarized_as_success(self) -> None:
        emit_event(event="failed", stage="extract", job_id="job-fb", error_code="BOT_CHECK", extra={"final": False})
        emit_event(event="succeeded", stage="postprocess", job_id="job-fb")
        self.store.flush()
        bundle = build_bundle(job_id="job-fb")
        self.assertEqual(bundle["summary"]["last_event"], "succeeded")
        self.assertEqual(bundle["summary"]["first_error"]["error_code"], "BOT_CHECK")


if __name__ == "__main__":
    unittest.main()
