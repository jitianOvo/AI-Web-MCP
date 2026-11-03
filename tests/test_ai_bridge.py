import asyncio
from pathlib import Path
import tempfile
import unittest

from aiohttp import ClientSession, web

from ai_web_mcp.bridge import SERVICE_KEY, create_app


class AiBridgeTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp_root = Path(__file__).resolve().parents[1] / "temp"
        temp_root.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=temp_root)
        self.headers = {"X-Bridge-Token": "fixture-token"}
        self.app = create_app({"host": "127.0.0.1", "port": 0, "bridge_token": "fixture-token", "debug": False,
                               "database_path": str(Path(self.temp.name) / "bridge.sqlite3"), "timeout_grace_ms": 0})
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        self.base = "http://127.0.0.1:" + str(self.site._server.sockets[0].getsockname()[1])
        self.session = ClientSession()
        self.image = Path(self.temp.name) / "fixture.png"
        self.image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()
        self.temp.cleanup()

    async def connect(self, provider="glm", target="fixture-glm", conversation="fixture-session"):
        ws = await self.session.ws_connect(self.base.replace("http:", "ws:") + "/ws/extension?token=fixture-token",
                                           headers={"Origin": "chrome-extension://fixture"})
        await ws.receive_json()
        url = ("https://chatglm.cn/main/alltoolsdetail?cid=" + conversation if provider == "glm" else "https://chatgpt.com/c/" + conversation)
        if not conversation:
            url = "https://chatglm.cn/main/alltoolsdetail" if provider == "glm" else "https://chatgpt.com/"
        await ws.send_json({"type": "hello", "provider": provider, "target_id": target, "tab_id": len(self.app[SERVICE_KEY].targets.connections),
                            "tab_bound": True, "page_ready": True, "tab_url": url, "conversation_id": conversation})
        await asyncio.sleep(0.01)
        return ws

    async def post(self, endpoint, payload):
        return await self.session.post(self.base + endpoint, headers=self.headers, json=payload)

    async def image_roundtrip(self, ws, **payload):
        task = asyncio.create_task(self.post("/api/chat/send-image", {"provider": "glm", "target_id": "fixture-glm",
            "image_path": str(self.image), "prompt": "", "timeout_ms": 2000, **payload}))
        message = await asyncio.wait_for(ws.receive_json(), 1)
        await ws.send_json({"type": "result", "request_id": message["request_id"], "conversation_id": "fixture-session",
                            "stage": "UPLOADED" if message["upload_only"] else "COMPLETED",
                            "result": "" if message["upload_only"] else "fixture-answer", "uploaded_image_count": 1})
        return message, await (await task).json()

    async def test_provider_routing_ambiguity_and_legacy_gpt_isolation(self):
        glm = await self.connect()
        legacy = await (await self.post("/api/chat/send", {"content": "hello"})).json()
        self.assertEqual(legacy["error"]["code"], "NO_READY_TARGET")
        gpt = await self.connect("chatgpt", "fixture-gpt")
        ambiguous = await (await self.post("/api/chat/send", {"content": "hello", "provider": ""})).json()
        self.assertEqual(ambiguous["error"]["code"], "TARGET_REQUIRED")
        call = asyncio.create_task(self.post("/api/chat/send", {"content": "hello", "provider": "glm", "request_id": "fixture-text", "timeout_ms": 2000}))
        message = await asyncio.wait_for(glm.receive_json(), 1)
        await glm.send_json({"type": "result", "request_id": message["request_id"], "conversation_id": "fixture-session", "result": "glm-answer"})
        self.assertEqual((await (await call).json())["provider"], "glm")
        replay = await (await self.post("/api/chat/send", {"content": "hello", "provider": "glm", "request_id": "fixture-text"})).json()
        self.assertTrue(replay["deduplicated"])
        await glm.close()
        await gpt.close()

    async def test_upload_is_only_upload_and_operation_fingerprints_differ(self):
        ws = await self.connect()
        upload, result = await self.image_roundtrip(ws, upload_only=True, request_id="fixture-upload")
        self.assertTrue(upload["upload_only"])
        self.assertEqual(upload["prompt"], "")
        self.assertEqual(result["stage"], "UPLOADED")
        self.assertEqual(result["result"], "")
        task = self.app[SERVICE_KEY].store.get_task("fixture-upload")
        self.assertEqual(task["stage"], "UPLOADED")
        vision, _ = await self.image_roundtrip(ws, request_id="fixture-vision")
        self.assertFalse(vision["upload_only"])
        first_fingerprint = task["fingerprint"]
        self.assertNotEqual(first_fingerprint, self.app[SERVICE_KEY].store.get_task("fixture-vision")["fingerprint"])
        sent, _ = await self.image_roundtrip(ws, image_path="", skip_paste=True, request_id="fixture-send")
        self.assertTrue(sent["skip_paste"])
        self.assertEqual(sent["prompt"], "")
        self.assertNotEqual(first_fingerprint, self.app[SERVICE_KEY].store.get_task("fixture-send")["fingerprint"])
        self.assertEqual(len(self.app[SERVICE_KEY].store.list_messages("fixture-session", 0, 100)), 2)
        await ws.close()

    async def test_reuploading_same_image_without_explicit_id_uploads_again(self):
        ws = await self.connect()
        first, _ = await self.image_roundtrip(ws, upload_only=True)
        second, _ = await self.image_roundtrip(ws, upload_only=True)
        self.assertNotEqual(first["request_id"], second["request_id"])
        await ws.close()

    async def test_second_upload_then_same_attachment_question_is_a_new_task(self):
        ws = await self.connect()
        await self.image_roundtrip(ws, upload_only=True, request_id="fixture-upload-a")
        first, _ = await self.image_roundtrip(ws, image_path="", skip_paste=True, request_id="fixture-send-a", prompt="what")
        self.image.write_bytes(b"\x89PNG\r\n\x1a\ndifferent-image")
        await self.image_roundtrip(ws, upload_only=True, request_id="fixture-upload-b")
        second, _ = await self.image_roundtrip(ws, image_path="", skip_paste=True, request_id="fixture-send-b", prompt="what")
        store = self.app[SERVICE_KEY].store
        self.assertNotEqual(store.get_task(first["request_id"])["fingerprint"], store.get_task(second["request_id"])["fingerprint"])
        await ws.close()

    async def test_new_chat_generation_and_explicit_id_recovery_after_cid_creation(self):
        ws = await self.connect(conversation="")
        first, _ = await self.image_roundtrip(ws)
        await ws.send_json({"type": "status", "provider": "glm", "target_id": "fixture-glm", "tab_id": 1,
                            "tab_bound": True, "page_ready": True, "conversation_id": "fixture-session",
                            "tab_url": "https://chatglm.cn/main/alltoolsdetail?cid=fixture-session"})
        await asyncio.sleep(0.01)
        replay = await (await self.post("/api/chat/send-image", {"provider": "glm", "target_id": "fixture-glm",
            "image_path": str(self.image), "prompt": "", "request_id": first["request_id"], "timeout_ms": 2000})).json()
        self.assertTrue(replay["deduplicated"])
        await ws.send_json({"type": "status", "provider": "glm", "target_id": "fixture-glm", "tab_id": 1,
                            "tab_bound": True, "page_ready": True, "is_new_chat": True, "conversation_id": "",
                            "tab_url": "https://chatglm.cn/main/alltoolsdetail"})
        await asyncio.sleep(0.01)
        second, _ = await self.image_roundtrip(ws)
        self.assertNotEqual(first["request_id"], second["request_id"])
        await ws.close()

    async def test_open_glm_ignores_navigation_only_parameters(self):
        ws = await self.connect()
        url = "https://chatglm.cn/main/alltoolsdetail?cid=fixture-session&t=123&lang=zh"
        task = asyncio.create_task(self.post("/api/tabs/open", {"provider": "glm", "url": url}))
        message = await asyncio.wait_for(ws.receive_json(), 1)
        self.assertEqual(message["provider"], "glm")
        target = self.app[SERVICE_KEY].targets.get("fixture-glm")
        await ws.send_json({"type": "open_result", "request_id": message["request_id"], "target_id": "fixture-glm",
                            "tab_id": target.state["tab_id"], "ready": True, "url": url, "conversation_id": "fixture-session", "reused": True})
        self.assertTrue((await (await task).json())["reused"])
        await ws.close()


if __name__ == "__main__":
    unittest.main()
