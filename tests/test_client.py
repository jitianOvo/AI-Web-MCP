import unittest
from unittest.mock import patch

from gpt_web_mcp.client import BridgeClient, BridgeError, normalize_chatgpt_url


class ClientStartupTests(unittest.TestCase):
    def test_history_urls_are_validated_and_canonicalized(self):
        for path in ("/c/old-123", "/g/g-project/c/old-123"):
            self.assertEqual(normalize_chatgpt_url("https://chatgpt.com" + path + "/", True), "https://chatgpt.com" + path)
        for url in ("https://evil.example/c/id", "https://chatgpt.com.evil/c/id", "http://chatgpt.com/c/id",
                    "https://user@chatgpt.com/c/id", "https://chatgpt.com:443/c/id", "https://chatgpt.com/c/id?q=x",
                    "https://chatgpt.com/c/id#x", "https://chatgpt.com/", "https://chatgpt.com/c/id/extra",
                    "https://chatgpt.com/\\evil", " https://chatgpt.com/c/id", ""):
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_chatgpt_url(url, True)

    def test_open_conversation_returns_target_and_never_sends_message(self):
        client = BridgeClient()
        opened = {"success": True, "ready": True, "target_id": "tab-7", "conversation_id": "old", "url": "https://chatgpt.com/c/old", "reused": True}
        with patch.object(client, "_request", return_value=opened) as request:
            self.assertEqual(client.open_conversation("https://chatgpt.com/c/old"), opened)
        request.assert_called_once_with("POST", "/api/tabs/open", {"url": "https://chatgpt.com/c/old"}, timeout=60)

    def test_open_conversation_rejects_unready_page(self):
        client = BridgeClient()
        with patch.object(client, "open_tab", return_value={"ready": False, "request_id": "original"}):
            with self.assertRaises(BridgeError) as error:
                client.open_conversation("https://chatgpt.com/c/old")
        self.assertEqual(error.exception.code, "TARGET_NOT_READY")

    def test_second_status_check_avoids_duplicate_start(self):
        client = BridgeClient()
        with patch.object(client, "status", side_effect=[BridgeError("BRIDGE_OFFLINE", "offline"), {"bridge": "online"}]), patch("gpt_web_mcp.client.subprocess.Popen") as popen:
            status = client.ensure_running()
        self.assertEqual(status["bridge"], "online")
        popen.assert_not_called()

    def test_offline_client_starts_once_and_waits_for_status(self):
        client = BridgeClient()
        with patch.object(client, "status", side_effect=[BridgeError("BRIDGE_OFFLINE", "offline"), BridgeError("BRIDGE_OFFLINE", "offline"), {"bridge": "online"}]), patch("gpt_web_mcp.client.subprocess.Popen") as popen, patch("gpt_web_mcp.client.time.sleep"):
            status = client.ensure_running(wait_seconds=1)
        self.assertEqual(status["bridge"], "online")
        popen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
