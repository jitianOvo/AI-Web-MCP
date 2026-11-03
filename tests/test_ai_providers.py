from contextlib import redirect_stdout
from io import StringIO
import json
import unittest
from unittest.mock import patch

from ai_web_mcp.ai_cli import main
from ai_web_mcp.client import BridgeClient, BridgeError
from ai_web_mcp.providers import normalize_ai_url, conversation_id_from_url, conversation_urls_match


class AiProviderTests(unittest.TestCase):
    def test_glm_identity_uses_cid_ignoring_time_and_language(self):
        first = "https://chatglm.cn/main/alltoolsdetail?t=123&cid=fixture-session&lang=zh"
        second = "https://chatglm.cn/main/alltoolsdetail?lang=en&cid=fixture-session&t=456"
        self.assertEqual(conversation_id_from_url("glm", first), "fixture-session")
        self.assertTrue(conversation_urls_match("glm", first, second))
        self.assertFalse(conversation_urls_match("glm", first, second.replace("fixture-session", "other")))
        for url in ("https://chatglm.cn.evil/main/alltoolsdetail?cid=id", "http://chatglm.cn/main/alltoolsdetail",
                    "https://user@chatglm.cn/main/alltoolsdetail", "https://chatglm.cn:443/main/alltoolsdetail",
                    "https://chatglm.cn/arbitrary?cid=id", "https://chatglm.cn/main/alltoolsdetail?cid=a&cid=b",
                    "https://chatglm.cn/main/alltoolsdetail?cid=", "https://chatglm.cn/main/alltoolsdetail?redirect=https://evil.example",
                    "https://chatglm.cn/main/alltoolsdetail#fragment"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                normalize_ai_url("glm", url)
        self.assertEqual(normalize_ai_url("gpt"), "https://chatgpt.com/")

    def test_client_routes_unique_provider_and_rejects_conflicting_target(self):
        client = BridgeClient()
        targets = [{"provider": p, "target_id": target, "tab_bound": True, "page_ready": True,
                    "conversation_id": "fixture-session"} for p, target in (("chatgpt", "gpt-tab"), ("glm", "glm-tab"))]
        with patch.object(client, "status", return_value={"targets": targets}), patch.object(client, "_request", return_value={"success": True}) as send:
            with self.assertRaises(BridgeError) as error:
                client.ask_ai("question")
            self.assertEqual(error.exception.code, "TARGET_REQUIRED")
            client.ask_ai("question", provider="glm", request_id="fixture-r")
            self.assertEqual(send.call_args.args[2]["target_id"], "glm-tab")
            with self.assertRaises(BridgeError) as error:
                client.ask_ai("question", provider="gpt", target_id="glm-tab")
            self.assertEqual(error.exception.code, "PROVIDER_MISMATCH")
            client.ask_ai("question", target_id="glm-tab")
            self.assertEqual(send.call_args.args[2]["provider"], "glm")

    def test_open_new_chat_drops_old_url_and_conversation(self):
        client = BridgeClient()
        old_url = "https://chatglm.cn/main/alltoolsdetail?cid=fixture-old"
        responses = [{"success": True, "target_id": "glm-tab", "url": old_url, "conversation_id": "fixture-old"},
                     {"success": True, "conversation_id": "", "is_new_chat": True}]
        with patch.object(client, "_request", side_effect=responses):
            result = client.open_ai_chat("glm", old_url, True)
        self.assertEqual(result["conversation_id"], "")
        self.assertEqual(result["url"], "https://chatglm.cn/main/alltoolsdetail")

    def test_cli_and_mcp_list_capabilities_without_sending(self):
        with redirect_stdout(StringIO()) as output:
            self.assertEqual(main(["providers"]), 0)
        self.assertEqual({p["provider"] for p in json.loads(output.getvalue())["providers"]}, {"chatgpt", "glm"})
        from ai_web_mcp import mcp_server
        tools = {tool.name for tool in mcp_server.mcp._tool_manager.list_tools()}
        self.assertTrue({"list_ai_providers", "list_ai_tabs", "open_ai_chat", "ask_ai", "ask_ai_image", "upload_ai_image", "send_ai_message"} <= tools)

    def test_cli_error_preserves_original_id_without_retry(self):
        with patch("ai_web_mcp.ai_cli.BridgeClient") as factory, redirect_stdout(StringIO()) as output:
            factory.return_value.ask_ai.side_effect = BridgeError("DELIVERY_UNCERTAIN", "lost response", "fixture-original")
            self.assertEqual(main(["ask", "--provider", "glm", "--question", "hello"]), 1)
            factory.return_value.ask_ai.assert_called_once()
        self.assertEqual(json.loads(output.getvalue())["request_id"], "fixture-original")

    def test_legacy_cli_does_not_select_glm(self):
        from ai_web_mcp.agent_cli import select_target
        with self.assertRaises(BridgeError) as error:
            select_target({"targets": [{"provider": "glm", "target_id": "glm-tab", "tab_bound": True, "page_ready": True}]})
        self.assertEqual(error.exception.code, "NO_READY_TARGET")


if __name__ == "__main__":
    unittest.main()
