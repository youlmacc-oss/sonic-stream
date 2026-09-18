import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

os.environ["SONICSTREAM_LOCATION"] = "server"
os.environ["SONICSTREAM_UI_DIR"] = ""

from app import web_session  # noqa: E402
from main import app  # noqa: E402


class WebSessionIsolationTests(unittest.TestCase):
    def setUp(self) -> None:
        web_session.reset_for_tests()
        self.client = TestClient(app)

    def test_sessions_do_not_share_keys_and_status_does_not_call_openai(self) -> None:
        calls = {"n": 0}

        def fake_verify(key: str) -> dict[str, str]:
            calls["n"] += 1
            if key.endswith("good"):
                return {"openai": "ready", "openai_label": "AI 연결됨"}
            return {"openai": "key_error", "openai_label": "AI 키가 올바르지 않습니다"}

        with patch("app.web_session.verify_session_key", side_effect=fake_verify):
            saved = self.client.post("/api/web/session", json={"openai_api_key": "sk-test-value-is-long-enough-good"})
            self.assertEqual(saved.status_code, 200)
            body = saved.json()
            self.assertEqual(body["openai"], "ready")
            self.assertNotIn("sk-test", str(body))
            other = TestClient(app)
            stranger = other.get("/api/status")
            self.assertEqual(stranger.status_code, 200)
            self.assertEqual(stranger.json()["openai"], "no_key")
            again = self.client.get("/api/status")
            self.assertEqual(again.json()["openai"], "ready")
            self.assertEqual(calls["n"], 1)

    def test_local_settings_stay_hidden_on_the_server(self) -> None:
        response = self.client.get("/api/local/settings")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
