import unittest
from unittest.mock import patch
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
import tempfile
import json

from ai_web_mcp.agent_cli import main, select_target
from ai_web_mcp.client import BridgeError


class AgentCliTests(unittest.TestCase):
    def test_vision_url_uses_bound_historical_target(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.png"
            image.write_bytes(b"image")
            with patch("ai_web_mcp.agent_cli.BridgeClient") as factory, redirect_stdout(StringIO()):
                client = factory.return_value
                client.open_conversation.return_value = {"target_id": "history"}
                client.status.return_value = {"targets": [{"target_id": "history", "tab_bound": True, "page_ready": True}]}
                client.send_image.return_value = {"success": True, "result": "seen"}
                self.assertEqual(main(["vision", "--image", str(image), "--url", "https://chatgpt.com/c/old"]), 0)
                client.open_conversation.assert_called_once_with("https://chatgpt.com/c/old")
                self.assertEqual(client.send_image.call_args.kwargs["target_id"], "history")

    def test_selects_only_ready_target_and_demands_choice_for_multiple(self):
        ready = {"target_id": "chrome", "tab_bound": True, "page_ready": True}
        status = {"targets": [{"target_id": "edge", "tab_bound": True, "page_ready": False}, ready]}
        self.assertEqual(select_target(status), "chrome")
        status["targets"].append({**ready, "target_id": "other"})
        with self.assertRaises(BridgeError) as error:
            select_target(status)
        self.assertEqual(error.exception.code, "TARGET_REQUIRED")
        self.assertEqual(select_target(status, "other"), "other")

    def test_failed_vision_is_called_once_and_preserves_request_id(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.png"
            image.write_bytes(b"image")
            with patch("ai_web_mcp.agent_cli.BridgeClient") as factory, redirect_stdout(StringIO()) as output:
                client = factory.return_value
                client.status.return_value = {"targets": [{"target_id": "t", "tab_bound": True, "page_ready": True}]}
                client.send_image.side_effect = BridgeError("DELIVERY_UNCERTAIN", "port closed", "original")
                self.assertEqual(main(["vision", "--image", str(image), "--request-id", "original"]), 1)
                client.send_image.assert_called_once()
                self.assertEqual(json.loads(output.getvalue())["request_id"], "original")

    def test_doctor_and_task_never_send(self):
        with patch("ai_web_mcp.agent_cli.BridgeClient") as factory, redirect_stdout(StringIO()):
            client = factory.return_value
            client.status.return_value = {"targets": []}
            client.task_status.return_value = {"success": True, "task": {"state": "completed"}}
            self.assertEqual(main(["doctor"]), 0)
            self.assertEqual(main(["task", "--request-id", "r"]), 0)
            client.send_image.assert_not_called()

    def test_automatic_id_survives_lost_reply_and_is_stable(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "image.png"
            image.write_bytes(b"image")
            with patch("ai_web_mcp.agent_cli.BridgeClient") as factory:
                client = factory.return_value
                client.status.return_value = {"targets": [{"target_id": "t", "tab_bound": True, "page_ready": True}]}
                client.send_image.side_effect = BridgeError("DELIVERY_UNCERTAIN", "port closed")
                results = []
                for _ in range(2):
                    with redirect_stdout(StringIO()) as output:
                        self.assertEqual(main(["vision", "--image", str(image)]), 1)
                    results.append(json.loads(output.getvalue()))
                self.assertTrue(results[0]["request_id"].startswith("img_"))
                self.assertEqual(results[0]["request_id"], results[1]["request_id"])
                self.assertEqual(client.send_image.call_args.kwargs["request_id"], results[0]["request_id"])
