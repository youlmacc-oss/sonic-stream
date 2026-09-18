from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.file_registry import register_saved_file
from app.history_store import save_history, load_history
from app.installer import installer_info
from app.jobs import JobStore
from app.local_runtime import evaluate_saved_media, resolve_managed_file, ManagedFileError
from app.transcript import empty_transcript, fetch_transcript, pick_caption_track
from app.ytdlp_engine import reset_ffmpeg_dir_cache, resolve_ffmpeg_dir, validate_url


class CompletionAndFileTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        os.environ["SONICSTREAM_HOME"] = str(self.dir)
        os.environ["SONICSTREAM_LOCATION"] = "local"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_empty_file_is_not_ok(self) -> None:
        empty = self.dir / "empty.mp4"
        empty.write_bytes(b"")
        verdict = evaluate_saved_media(empty, "video")
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["code"], "PROCESS_FAILED")

    def test_non_media_bytes_fail_when_probe_fails(self) -> None:
        junk = self.dir / "junk.mp4"
        junk.write_bytes(b"not-a-video")
        with patch("app.local_runtime.probe_media", return_value={"ok": False, "error": "ffprobe_failed"}):
            verdict = evaluate_saved_media(junk, "video")
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["code"], "VERIFY_FAILED")

    def test_missing_ffprobe_is_unavailable_not_success(self) -> None:
        junk = self.dir / "maybe.mp4"
        junk.write_bytes(b"xxxxxxxxxxx")
        with patch("app.local_runtime.probe_media", return_value={"ok": False, "error": "ffprobe_unavailable"}):
            verdict = evaluate_saved_media(junk, "video")
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["code"], "VERIFY_UNAVAILABLE")

    def test_video_without_video_stream_fails(self) -> None:
        path = self.dir / "audio-only.mp4"
        path.write_bytes(b"12345678901")
        with patch(
            "app.local_runtime.probe_media",
            return_value={"ok": True, "has_video": False, "has_audio": True},
        ):
            verdict = evaluate_saved_media(path, "video", source_has_audio=True)
        self.assertFalse(verdict["ok"])
        self.assertEqual(verdict["code"], "VERIFY_FAILED")

    def test_silent_original_video_allowed(self) -> None:
        path = self.dir / "silent.mp4"
        path.write_bytes(b"12345678901")
        with patch(
            "app.local_runtime.probe_media",
            return_value={"ok": True, "has_video": True, "has_audio": False, "width": 720, "height": 1280},
        ):
            verdict = evaluate_saved_media(path, "video", source_has_audio=False)
        self.assertTrue(verdict["ok"])

    def test_previous_folder_file_opens_via_registry(self) -> None:
        old = self.dir / "old" / "clip.mp4"
        old.parent.mkdir()
        old.write_bytes(b"12345678901")
        register_saved_file(old, job_id="job-1")
        os.environ["SONICSTREAM_SAVE_DIR"] = str(self.dir / "new")
        (self.dir / "new").mkdir()
        found = resolve_managed_file(str(old))
        self.assertEqual(found, old.resolve())

    def test_unregistered_outside_file_forbidden(self) -> None:
        outsider = self.dir / "secret.exe"
        outsider.write_bytes(b"12345678901")
        os.environ["SONICSTREAM_SAVE_DIR"] = str(self.dir / "new")
        (self.dir / "new").mkdir()
        with self.assertRaises(ManagedFileError) as ctx:
            resolve_managed_file(str(outsider))
        self.assertEqual(ctx.exception.code, "FORBIDDEN")

    def test_invalid_youtube_id_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_url("https://www.youtube.com/watch?v=dUpHist99")

    def test_valid_youtube_id_passes(self) -> None:
        self.assertTrue(validate_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ"))

    def test_ffmpeg_exists_permission_error_is_skipped(self) -> None:
        reset_ffmpeg_dir_cache()
        os.environ.pop("SONICSTREAM_FFMPEG_DIR", None)
        os.environ.pop("FFMPEG_LOCATION", None)
        blocked = Path(self.dir) / "blocked"
        with patch("app.ytdlp_engine.shutil.which", return_value=None):
            with patch("app.ytdlp_engine.Path.exists", side_effect=PermissionError("denied")):
                self.assertIsNone(resolve_ffmpeg_dir())

    def test_cancel_blocks_done(self) -> None:
        store = JobStore()
        store.create("j1", "video", "1080p")
        store.mark_worker("j1", True)
        store.request_cancel("j1")
        settled = store.settle("j1", "done", verified=True)
        self.assertIsNotNone(settled)
        self.assertEqual(settled.status, "error")
        self.assertEqual(settled.error_code, "CANCELLED")

    def test_queued_cancel_settles(self) -> None:
        store = JobStore()
        store.create("j2", "video", "1080p")
        store.request_cancel("j2")
        job = store.get("j2")
        self.assertEqual(job.status, "error")
        self.assertTrue(job.settled)

    def test_installer_available_false_without_file(self) -> None:
        os.environ["SONICSTREAM_INSTALLER_PATH"] = str(self.dir / "missing.zip")
        info = installer_info("http://127.0.0.1:8011/")
        self.assertFalse(info["available"])

    def test_history_roundtrip(self) -> None:
        saved = save_history([{"id": "1", "url": "https://youtu.be/dQw4w9WgXcQ", "title": "a"}])
        self.assertEqual(len(saved), 1)
        self.assertEqual(load_history()[0]["id"], "1")

    def test_caption_prefers_vtt_over_srv3(self) -> None:
        info = {
            "subtitles": {
                "ko": [
                    {"ext": "srv3", "url": "http://example/srv3"},
                    {"ext": "vtt", "url": "http://example/vtt"},
                ]
            }
        }
        lang, automatic, track = pick_caption_track(info)
        self.assertEqual(track["ext"], "vtt")
        self.assertFalse(automatic)

    def test_transcript_network_failure_not_cached(self) -> None:
        with patch("app.transcript.validate_url", return_value="https://youtu.be/dQw4w9WgXcQ"):
            with patch("app.transcript.canonicalize_media_url", return_value="https://youtu.be/dQw4w9WgXcQ"):
                with patch("app.transcript.YoutubeDL") as ydl:
                    ydl.side_effect = RuntimeError("network down")
                    first = fetch_transcript("https://youtu.be/dQw4w9WgXcQ")
        self.assertEqual(first["code"], "NETWORK_ERROR")
        self.assertTrue(first["error"])


if __name__ == "__main__":
    unittest.main()
