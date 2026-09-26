import unittest
from unittest.mock import patch

from gpt_web_mcp.client import BridgeClient, BridgeError


class ClientStartupTests(unittest.TestCase):
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
