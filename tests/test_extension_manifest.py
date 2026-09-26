import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ExtensionManifestTests(unittest.TestCase):
    def test_manifest_and_referenced_files_exist(self):
        manifest_path = ROOT / "extension" / "manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(manifest["manifest_version"], 3)
        self.assertIn("background.js", manifest["background"]["service_worker"])
        for script in ["background.js", "selectors.js", "content.js", "popup.js", "popup.css", "popup.html", "config.js"]:
            self.assertTrue((ROOT / "extension" / script).exists(), script)
        self.assertIn("https://chatgpt.com/*", manifest["host_permissions"])
        self.assertIn("storage", manifest["permissions"])

    def test_popup_contains_actionable_connection_diagnostics(self):
        popup = (ROOT / "extension" / "popup.js").read_text(encoding="utf-8")
        self.assertIn("Bridge 未连接", popup)
        self.assertIn("请打开 ChatGPT 标签页并点击绑定按钮", popup)
        self.assertIn("页面脚本未就绪", popup)

    def test_background_buffers_events_while_bridge_is_disconnected(self):
        background = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("pendingBridgeEvents", background)
        self.assertIn("replayPendingEvents", background)
        self.assertIn("MAX_PENDING_EVENTS", background)

    def test_background_persists_and_restores_bound_targets(self):
        background = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("boundTabs", background)
        self.assertIn("chrome.storage.local.get", background)
        self.assertIn("for (const targetId of Object.keys(boundTabs)) connectBridge(targetId)", background)

    def test_content_has_conversation_turn_fallback(self):
        selectors = (ROOT / "extension" / "selectors.js").read_text(encoding="utf-8")
        content = (ROOT / "extension" / "content.js").read_text(encoding="utf-8")
        self.assertIn("conversationTurn", selectors)
        self.assertIn("roleFromNode", content)
        self.assertIn("main article", selectors)

    def test_background_auto_binds_single_chatgpt_tab(self):
        background = (ROOT / "extension" / "background.js").read_text(encoding="utf-8")
        self.assertIn("autoBindSingleTab", background)
        self.assertIn("chatgptTabs", background)
        self.assertIn("chrome.tabs.query", background)
        self.assertIn("tabs.length !== 1", background)
        self.assertIn("bind_specific_tab", background.replace("bindSpecificTab", "bind_specific_tab"))
        self.assertIn("bound_result", background)

    def test_content_reports_page_streaming_state(self):
        content = (ROOT / "extension" / "content.js").read_text(encoding="utf-8")
        self.assertIn("bridge_state", content)
        self.assertIn("generating", content)
        self.assertIn("conversation_title", content)


if __name__ == "__main__":
    unittest.main()
