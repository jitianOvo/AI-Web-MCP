import asyncio
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from aiohttp import ClientSession, web

from ai_web_mcp.bridge import SERVICE_KEY, create_app
from ai_web_mcp import __version__ as bridge_version


class BridgeRoundTripTests(unittest.IsolatedAsyncioTestCase):
    async def test_open_history_url_contract_and_error_propagation(self):
        headers = {"X-Bridge-Token": self.token}
        invalid = await self.session.post(self.base_url + "/api/tabs/open", headers=headers, json={"url": "https://evil.example/c/id"})
        self.assertEqual((await invalid.json())["error"]["code"], "INVALID_CHATGPT_URL")
        ws = await self.session.ws_connect(self.ws_url, headers={"Origin": "chrome-extension://fixture"})
        await ws.receive_json()
        await ws.send_json({"type": "hello", "target_id": "unbound", "tab_bound": False, "page_ready": False})
        url = "https://chatgpt.com/c/old-123"
        task = asyncio.create_task(self.session.post(self.base_url + "/api/tabs/open", headers=headers, json={"url": url}))
        message = await ws.receive_json()
        self.assertEqual(message["url"], url)
        await ws.send_json({"type": "open_result", "request_id": message["request_id"], "tab_id": 7,
                           "target_id": "tab-7", "ready": True, "url": url, "conversation_id": "old-123", "reused": True})
        # A successful browser reply alone must not expose an unregistered target.
        await asyncio.sleep(0.1)
        self.assertFalse(task.done())
        target_ws = await self.session.ws_connect(self.ws_url, headers={"Origin": "chrome-extension://fixture"})
        await target_ws.receive_json()
        await target_ws.send_json({"type": "hello", "target_id": "tab-7", "tab_id": 7,
                                   "tab_bound": True, "page_ready": True, "tab_url": "https://chatgpt.com/c/wrong"})
        await asyncio.sleep(0.1)
        self.assertFalse(task.done())
        await target_ws.send_json({"type": "status", "target_id": "tab-7", "tab_id": 7,
                                   "tab_bound": True, "page_ready": True, "tab_url": url})
        body = await (await task).json()
        self.assertEqual(body["conversation_id"], "old-123")
        self.assertEqual(body["url"], url)
        self.assertTrue(body["reused"])
        task = asyncio.create_task(self.session.post(self.base_url + "/api/tabs/open", headers=headers, json={"url": url}))
        message = await ws.receive_json()
        await ws.send_json({"type": "error", "request_id": message["request_id"], "code": "CONVERSATION_URL_MISMATCH", "message": "redirected"})
        body = await (await task).json()
        self.assertEqual(body["error"]["code"], "CONVERSATION_URL_MISMATCH")
        await target_ws.close()
        await ws.close()

    async def test_open_target_without_registration_fails_instead_of_success(self):
        ws = await self.session.ws_connect(self.ws_url, headers={"Origin": "chrome-extension://fixture"})
        await ws.receive_json()
        await ws.send_json({"type": "hello", "target_id": "unbound", "tab_bound": False})
        with patch("ai_web_mcp.bridge.OPEN_TARGET_READY_TIMEOUT", 0.1):
            task = asyncio.create_task(self.session.post(self.base_url + "/api/tabs/open",
                headers={"X-Bridge-Token": self.token}, json={"url": "https://chatgpt.com/c/missing"}))
            message = await ws.receive_json()
            await ws.send_json({"type": "open_result", "request_id": message["request_id"], "target_id": "tab-missing", "tab_id": 99, "ready": True})
            body = await (await task).json()
        self.assertFalse(body["success"])
        self.assertEqual(body["error"]["code"], "TARGET_NOT_READY")
        self.assertFalse(self.app[SERVICE_KEY].open_waiters)
        await ws.close()

    async def asyncSetUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.token = "fixture-token"
        self.config = {
            "host": "127.0.0.1",
            "port": 0,
            "bridge_token": self.token,
            "response_timeout": 3,
            "timeout_grace_ms": 10,
            "max_queue_size": 5,
            "max_text_chars": 10000,
            "database_path": str(Path(self.temp_dir.name) / "bridge.sqlite3"),
            "debug": False,
        }
        self.app = create_app(self.config)
        self.runner = web.AppRunner(self.app, access_log=None)
        await self.runner.setup()
        self.site = web.TCPSite(self.runner, "127.0.0.1", 0)
        await self.site.start()
        port = self.site._server.sockets[0].getsockname()[1]
        self.base_url = f"http://127.0.0.1:{port}"
        self.ws_url = f"ws://127.0.0.1:{port}/ws/extension?token={self.token}"
        self.session = ClientSession()

    async def asyncTearDown(self):
        await self.session.close()
        await self.runner.cleanup()
        self.temp_dir.cleanup()

    async def test_extension_round_trip_and_message_read(self):
        ws = await self.session.ws_connect(self.ws_url, headers={"Origin": "chrome-extension://fixture"})
        ready = await ws.receive_json()
        self.assertEqual(ready["type"], "bridge_ready")
        await ws.send_json({
            "type": "hello", "tab_bound": True, "page_ready": True,
            "target_id": "fixture-tab", "tab_id": 7, "tab_title": "ChatGPT",
            "tab_url": "https://chatgpt.com/c/fixture",
        })

        headers = {"X-Bridge-Token": self.token}
        send_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/send", headers=headers,
            json={"request_id": "fixture-request", "content": "hello", "timeout_ms": 2000},
        ))
        task = await ws.receive_json()
        self.assertEqual(task["type"], "task")
        self.assertEqual(task["prompt"], "hello")
        await ws.send_json({
            "type": "result", "request_id": "fixture-request",
            "conversation_id": "fixture-conversation", "message_id": "assistant-1",
            "result": "world",
        })
        response = await send_task
        self.assertEqual(response.status, 200)
        body = await response.json()
        self.assertEqual(body["result"], "world")
        self.assertEqual(body["conversation_id"], "fixture-conversation")

        read = await self.session.get(
            self.base_url + "/api/chat/messages?conversation_id=fixture-conversation",
            headers=headers,
        )
        read_body = await read.json()
        self.assertEqual([item["content"] for item in read_body["messages"]], ["world"])

        sync_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/sync", headers=headers,
            json={"conversation_id": "current"},
        ))
        sync_request = await ws.receive_json()
        self.assertEqual(sync_request["type"], "sync")
        await ws.send_json({
            "type": "sync_result", "request_id": sync_request["request_id"],
            "conversation_id": "fixture-conversation",
            "messages": [{"message_id": "user-1", "role": "user", "content": "hello", "content_hash": "user-hash"}],
        })
        sync_response = await sync_task
        sync_body = await sync_response.json()
        self.assertEqual(sync_body["conversation_id"], "fixture-conversation")
        self.assertEqual([item["content"] for item in sync_body["messages"]], ["world", "hello"])

        wait_task = asyncio.create_task(self.session.get(
            self.base_url + "/api/chat/wait?conversation_id=fixture-conversation&after=2&timeout_ms=2000",
            headers=headers,
        ))
        await asyncio.sleep(0.05)
        await ws.send_json({
            "type": "message_event", "conversation_id": "fixture-conversation",
            "message": {"message_id": "assistant-2", "role": "assistant", "content": "new", "content_hash": "new-hash"},
        })
        wait_response = await wait_task
        wait_body = await wait_response.json()
        self.assertFalse(wait_body["timed_out"])
        self.assertEqual(wait_body["messages"][-1]["content"], "new")
        await ws.close()

    async def test_active_request_can_be_cancelled(self):
        ws = await self.session.ws_connect(self.ws_url, headers={"Origin": "chrome-extension://fixture"})
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "fixture-tab", "tab_id": 7})
        headers = {"X-Bridge-Token": self.token}
        send_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/send", headers=headers,
            json={"request_id": "cancel-request", "content": "cancel me", "timeout_ms": 2000},
        ))
        task = await ws.receive_json()
        self.assertEqual(task["request_id"], "cancel-request")
        cancel_response = await self.session.post(self.base_url + "/api/chat/cancel/cancel-request", headers=headers)
        self.assertTrue((await cancel_response.json())["cancelled"])
        cancel_message = await ws.receive_json()
        self.assertEqual(cancel_message["type"], "cancel")
        response = await send_task
        self.assertEqual(response.status, 499)
        self.assertEqual((await response.json())["error"]["code"], "REQUEST_CANCELLED")
        await ws.close()

    async def test_empty_response_is_rejected(self):
        ws = await self.session.ws_connect(self.ws_url, headers={"Origin": "chrome-extension://fixture"})
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "empty-target", "tab_id": 10})
        headers = {"X-Bridge-Token": self.token}
        request_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/send", headers=headers,
            json={"request_id": "empty-request", "target_id": "empty-target", "content": "empty", "timeout_ms": 100},
        ))
        task = await ws.receive_json()
        await ws.send_json({"type": "result", "request_id": task["request_id"], "target_id": "empty-target", "result": ""})
        response = await request_task
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())["error"]["code"], "EMPTY_RESPONSE")
        await ws.close()

    async def test_page_error_from_extension_is_returned_structured(self):
        ws = await self.session.ws_connect(self.ws_url, headers={"Origin": "chrome-extension://fixture"})
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "page-error-target", "tab_id": 12})
        headers = {"X-Bridge-Token": self.token}
        request_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/send", headers=headers,
            json={"request_id": "page-error-request", "target_id": "page-error-target", "content": "error", "timeout_ms": 100},
        ))
        task = await ws.receive_json()
        await ws.send_json({"type": "error", "request_id": task["request_id"], "target_id": "page-error-target", "code": "CHATGPT_PAGE_ERROR", "message": "fixture page error"})
        response = await request_task
        self.assertEqual(response.status, 503)
        body = await response.json()
        self.assertEqual(body["error"]["code"], "CHATGPT_PAGE_ERROR")
        self.assertEqual(body["error"]["message"], "fixture page error")
        await ws.close()

    async def test_response_timeout_sends_cancel(self):
        ws = await self.session.ws_connect(self.ws_url, headers={"Origin": "chrome-extension://fixture"})
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "timeout-target", "tab_id": 11})
        headers = {"X-Bridge-Token": self.token}
        request_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/send", headers=headers,
            json={"request_id": "timeout-request", "target_id": "timeout-target", "content": "timeout", "timeout_ms": 20},
        ))
        task = await ws.receive_json()
        self.assertEqual(task["request_id"], "timeout-request")
        cancel = await ws.receive_json()
        self.assertEqual(cancel["type"], "cancel")
        response = await request_task
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())["error"]["code"], "RESPONSE_TIMEOUT")
        await ws.close()

    async def test_wait_event_reports_timeout_without_messages(self):
        headers = {"X-Bridge-Token": self.token}
        response = await self.session.get(
            self.base_url + "/api/chat/wait?conversation_id=empty&after=0&timeout_ms=50",
            headers=headers,
        )
        self.assertEqual(response.status, 200)
        body = await response.json()
        self.assertTrue(body["timed_out"])
        self.assertEqual(body["messages"], [])

    async def test_status_has_version_and_shutdown_endpoint(self):
        headers = {"X-Bridge-Token": self.token}
        status = await self.session.get(self.base_url + "/api/status", headers=headers)
        status_body = await status.json()
        self.assertEqual(status_body["status"]["bridge_version"], bridge_version)
        shutdown = await self.session.post(self.base_url + "/api/shutdown", headers=headers)
        self.assertTrue((await shutdown.json())["shutting_down"])

    async def test_search_and_export_return_persisted_content(self):
        headers = {"Origin": "chrome-extension://fixture"}
        ws = await self.session.ws_connect(self.ws_url, headers=headers)
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "export-target", "tab_id": 8})
        token_headers = {"X-Bridge-Token": self.token}
        await ws.send_json({"type": "message_event", "conversation_id": "export-conversation", "message": {"message_id": "m1", "role": "user", "content": "searchable phrase", "content_hash": "export-h1"}})
        await asyncio.sleep(0.05)
        search = await self.session.get(self.base_url + "/api/chat/search?q=searchable&conversation_id=export-conversation", headers=token_headers)
        search_body = await search.json()
        self.assertEqual(search_body["messages"][0]["message_id"], "m1")
        export = await self.session.get(self.base_url + "/api/chat/export?conversation_id=export-conversation&format=markdown", headers=token_headers)
        export_body = await export.json()
        self.assertIn("searchable phrase", export_body["content"])
        self.assertEqual(export_body["format"], "markdown")
        await ws.close()

    async def test_target_id_routes_tasks_to_selected_connection(self):
        headers = {"Origin": "chrome-extension://fixture"}
        ws_a = await self.session.ws_connect(self.ws_url, headers=headers)
        ws_b = await self.session.ws_connect(self.ws_url, headers=headers)
        await ws_a.receive_json()
        await ws_b.receive_json()
        await ws_a.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "target-a", "tab_id": 1, "browser": "edge", "browser_version": "140.0"})
        await ws_b.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "target-b", "tab_id": 2, "browser": "chrome", "browser_version": "139.0"})
        token_headers = {"X-Bridge-Token": self.token}
        status = await self.session.get(self.base_url + "/api/status", headers=token_headers)
        status_body = await status.json()
        self.assertEqual({item["target_id"] for item in status_body["status"]["targets"]}, {"target-a", "target-b"})
        target_status = {item["target_id"]: item for item in status_body["status"]["targets"]}
        self.assertEqual(target_status["target-a"]["browser_version"], "140.0")

        send_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/send", headers=token_headers,
            json={"request_id": "target-b-request", "target_id": "target-b", "content": "only B", "timeout_ms": 2000},
        ))
        task_b = await ws_b.receive_json()
        self.assertEqual(task_b["target_id"], "target-b")
        self.assertEqual(task_b["prompt"], "only B")
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ws_a.receive(), timeout=0.05)
        await ws_b.send_json({"type": "result", "request_id": "target-b-request", "conversation_id": "conversation-b", "result": "B result"})
        response = await send_task
        self.assertEqual((await response.json())["result"], "B result")
        await ws_a.close()
        await ws_b.close()

    async def test_persona_is_persisted_and_applied_to_task_prompt(self):
        ws = await self.session.ws_connect(self.ws_url, headers={"Origin": "chrome-extension://fixture"})
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "persona-target", "tab_id": 3})
        headers = {"X-Bridge-Token": self.token}
        persona_response = await self.session.post(
            self.base_url + "/api/personas", headers=headers,
            json={"persona_id": "critic", "name": "批评者", "system_prompt": "指出前提漏洞，给出反例。"},
        )
        self.assertEqual(persona_response.status, 200)
        self.assertEqual((await persona_response.json())["persona"]["persona_id"], "critic")
        send_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/send", headers=headers,
            json={"request_id": "persona-request", "target_id": "persona-target", "persona_id": "critic", "content": "分析方案", "timeout_ms": 2000},
        ))
        task = await ws.receive_json()
        self.assertIn("PERSONA INSTRUCTION", task["prompt"])
        self.assertIn("指出前提漏洞", task["prompt"])
        await ws.send_json({"type": "result", "request_id": "persona-request", "conversation_id": "persona-conversation", "result": "已指出反例"})
        response = await send_task
        self.assertEqual((await response.json())["result"], "已指出反例")
        personas = await self.session.get(self.base_url + "/api/personas", headers=headers)
        self.assertEqual(len((await personas.json())["personas"]), 1)
        await ws.close()

    async def test_task_group_runs_tasks_and_persists_status(self):
        headers = {"Origin": "chrome-extension://fixture"}
        ws_a = await self.session.ws_connect(self.ws_url, headers=headers)
        ws_b = await self.session.ws_connect(self.ws_url, headers=headers)
        await ws_a.receive_json()
        await ws_b.receive_json()
        await ws_a.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "group-a", "tab_id": 4})
        await ws_b.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "group-b", "tab_id": 5})
        token_headers = {"X-Bridge-Token": self.token}
        persona_response = await self.session.post(
            self.base_url + "/api/personas", headers=token_headers,
            json={"persona_id": "critic", "name": "批评者", "system_prompt": "寻找风险。"},
        )
        self.assertEqual(persona_response.status, 200)
        group_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/task-groups/group-fixture/submit", headers=token_headers,
            json={"title": "双角色分析", "tasks": [
                {"target_id": "group-a", "persona_id": "critic", "content": "统一问题", "timeout_ms": 2000},
                {"target_id": "group-b", "content": "统一问题", "timeout_ms": 2000},
            ]},
        ))
        task_a = await ws_a.receive_json()
        self.assertEqual(task_a["target_id"], "group-a")
        await ws_a.send_json({"type": "result", "request_id": task_a["request_id"], "conversation_id": "group-a-conversation", "result": "风险结论"})
        task_b = await ws_b.receive_json()
        self.assertEqual(task_b["target_id"], "group-b")
        await ws_b.send_json({"type": "result", "request_id": task_b["request_id"], "conversation_id": "group-b-conversation", "result": "执行结论"})
        group_response = await group_task
        group_body = await group_response.json()
        self.assertEqual(group_body["state"], "completed")
        self.assertEqual([item["result"] for item in group_body["results"]], ["风险结论", "执行结论"])
        self.assertIn("风险结论", group_body["merged_markdown"])
        self.assertEqual(len(group_body["conflict_candidates"]), 1)
        status_response = await self.session.get(self.base_url + "/api/task-groups/group-fixture", headers=token_headers)
        status_body = await status_response.json()
        self.assertEqual(status_body["task_group"]["state"], "completed")
        self.assertEqual(len(status_body["task_group"]["tasks"]), 2)
        await ws_a.close()
        await ws_b.close()

    async def test_ready_targets_process_tasks_independently(self):
        headers = {"Origin": "chrome-extension://fixture"}
        ws_a = await self.session.ws_connect(self.ws_url, headers=headers)
        ws_b = await self.session.ws_connect(self.ws_url, headers=headers)
        await ws_a.receive_json()
        await ws_b.receive_json()
        await ws_a.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "parallel-a", "tab_id": 6})
        await ws_b.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "parallel-b", "tab_id": 7})
        token_headers = {"X-Bridge-Token": self.token}
        send_a = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/send", headers=token_headers,
            json={"request_id": "parallel-a-request", "target_id": "parallel-a", "content": "A", "timeout_ms": 2000},
        ))
        send_b = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/send", headers=token_headers,
            json={"request_id": "parallel-b-request", "target_id": "parallel-b", "content": "B", "timeout_ms": 2000},
        ))
        task_a = await ws_a.receive_json()
        task_b = await ws_b.receive_json()
        self.assertEqual(task_a["request_id"], "parallel-a-request")
        self.assertEqual(task_b["request_id"], "parallel-b-request")
        await ws_a.send_json({"type": "result", "request_id": task_a["request_id"], "conversation_id": "parallel-a-conversation", "result": "A result"})
        await ws_b.send_json({"type": "result", "request_id": task_b["request_id"], "conversation_id": "parallel-b-conversation", "result": "B result"})
        self.assertEqual((await (await send_a).json())["result"], "A result")
        self.assertEqual((await (await send_b).json())["result"], "B result")
        await ws_a.close()
        await ws_b.close()

    async def test_rate_limit_waits_between_dispatch_slots(self):
        service = self.app[SERVICE_KEY]
        service.config["rate_limit_per_minute"] = 1
        service.config["rate_limit_window_sec"] = 0.05
        started = asyncio.get_running_loop().time()
        await service.wait_for_rate_limit()
        await service.wait_for_rate_limit()
        self.assertGreaterEqual(asyncio.get_running_loop().time() - started, 0.04)

    async def test_disconnected_target_fails_only_its_active_request(self):
        headers = {"Origin": "chrome-extension://fixture"}
        ws = await self.session.ws_connect(self.ws_url, headers=headers)
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "disconnect-target", "tab_id": 9})
        token_headers = {"X-Bridge-Token": self.token}
        request_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/chat/send", headers=token_headers,
            json={"request_id": "disconnect-request", "target_id": "disconnect-target", "content": "wait", "timeout_ms": 2000},
        ))
        task = await ws.receive_json()
        self.assertEqual(task["request_id"], "disconnect-request")
        await ws.close()
        response = await request_task
        self.assertEqual(response.status, 503)
        self.assertEqual((await response.json())["error"]["code"], "EXTENSION_DISCONNECTED")

    async def test_tabs_list_and_bind_via_control_socket(self):
        headers = {"Origin": "chrome-extension://fixture"}
        ws = await self.session.ws_connect(self.ws_url, headers=headers)
        await ws.receive_json()
        await ws.send_json({
            "type": "hello", "tab_bound": True, "page_ready": True, "target_id": "fixture-tab", "tab_id": 7,
            "tabs": [{"tab_id": 7, "tab_title": "ChatGPT", "tab_url": "https://chatgpt.com/c/fixture", "active": True, "window_id": 1}],
        })
        token_headers = {"X-Bridge-Token": self.token}
        tabs = await self.session.get(self.base_url + "/api/tabs", headers=token_headers)
        tabs_body = await tabs.json()
        self.assertEqual(tabs_body["count"], 1)
        self.assertEqual(tabs_body["tabs"][0]["bound_target_id"], "fixture-tab")
        bind_task = asyncio.create_task(self.session.post(
            self.base_url + "/api/tabs/bind", headers=token_headers, json={"tab_id": 9},
        ))
        bind_message = await ws.receive_json()
        self.assertEqual(bind_message["type"], "bind_tab")
        self.assertEqual(bind_message["tab_id"], 9)
        await ws.send_json({
            "type": "bound_result", "request_id": bind_message["request_id"], "target_id": "tab-9", "title": "New Chat", "success": True,
        })
        bind_body = await (await bind_task).json()
        self.assertEqual(bind_body["target_id"], "tab-9")
        await ws.close()

    async def test_latest_message_endpoint_returns_most_recent(self):
        headers = {"Origin": "chrome-extension://fixture"}
        ws = await self.session.ws_connect(self.ws_url, headers=headers)
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "latest-target", "tab_id": 14})
        for index, content in enumerate(["first", "second"]):
            await ws.send_json({"type": "message_event", "conversation_id": "latest-conversation", "message": {"message_id": f"assistant-{index}", "role": "assistant", "content": content, "content_hash": f"hash-{index}"}})
        await asyncio.sleep(0.05)
        response = await self.session.get(
            self.base_url + "/api/chat/latest?conversation_id=latest-conversation", headers={"X-Bridge-Token": self.token},
        )
        body = await response.json()
        self.assertEqual(body["message"]["content"], "second")
        self.assertEqual(body["response_state"], "idle")
        await ws.close()

    async def test_open_tab_new_chat_and_pause(self):
        headers = {"Origin": "chrome-extension://fixture"}
        ws = await self.session.ws_connect(self.ws_url, headers=headers)
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "v4-target", "tab_id": 20})
        token_headers = {"X-Bridge-Token": self.token}
        open_task = asyncio.create_task(self.session.post(self.base_url + "/api/tabs/open", headers=token_headers))
        open_message = await ws.receive_json()
        self.assertEqual(open_message["type"], "open_tab")
        await ws.send_json({"type": "open_result", "request_id": open_message["request_id"], "tab_id": 21, "target_id": "tab-21", "ready": True, "success": True})
        await ws.send_json({"type": "status", "target_id": "tab-21", "tab_id": 21, "tab_bound": True, "page_ready": True, "tab_url": "https://chatgpt.com/"})
        open_body = await (await open_task).json()
        self.assertEqual(open_body["target_id"], "tab-21")
        new_task = asyncio.create_task(self.session.post(self.base_url + "/api/chat/new", headers=token_headers, json={}))
        new_message = await ws.receive_json()
        self.assertEqual(new_message["type"], "new_chat")
        await ws.send_json({"type": "new_chat_result", "request_id": new_message["request_id"], "conversation_id": "fresh", "is_new_chat": True, "success": True})
        new_body = await (await new_task).json()
        self.assertTrue(new_body["is_new_chat"])
        pause = await self.session.post(self.base_url + "/api/pause", headers=token_headers)
        self.assertTrue((await pause.json())["paused"])
        paused_send = await self.session.post(self.base_url + "/api/chat/send", headers=token_headers, json={"content": "x", "timeout_ms": 50})
        self.assertEqual((await paused_send.json())["error"]["code"], "PAUSED")
        resume = await self.session.post(self.base_url + "/api/resume", headers=token_headers)
        self.assertFalse((await resume.json())["paused"])
        await ws.close()

    async def test_sync_state_reports_page_snapshot(self):
        headers = {"Origin": "chrome-extension://fixture"}
        ws = await self.session.ws_connect(self.ws_url, headers=headers)
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "state-target", "tab_id": 22})
        task = asyncio.create_task(self.session.post(self.base_url + "/api/chat/sync-state", headers={"X-Bridge-Token": self.token}, json={"conversation_id": "state-conv"}))
        sync_message = await ws.receive_json()
        self.assertEqual(sync_message["type"], "sync")
        await ws.send_json({"type": "sync_result", "request_id": sync_message["request_id"], "conversation_id": "state-conv", "messages": [{"message_id": "u1", "role": "user", "content": "hi", "content_hash": "h1"}]})
        state_message = await ws.receive_json()
        self.assertEqual(state_message["type"], "check_state")
        await ws.send_json({"type": "state_result", "request_id": state_message["request_id"], "state": {"user_message_on_screen": True, "assistant_present": True, "last_text": "ok", "generating": False, "page_ready": True, "input_ready": True, "is_new_chat": False, "conversation_id": "state-conv"}})
        body = await (await task).json()
        self.assertTrue(body["success"])
        self.assertTrue(body["user_message_on_screen"])
        self.assertEqual(body["last_text"], "ok")
        await ws.close()

    async def test_progress_stage_is_persisted(self):
        headers = {"Origin": "chrome-extension://fixture"}
        ws = await self.session.ws_connect(self.ws_url, headers=headers)
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "stage-target", "tab_id": 23})
        token_headers = {"X-Bridge-Token": self.token}
        send_task = asyncio.create_task(self.session.post(self.base_url + "/api/chat/send", headers=token_headers, json={"request_id": "stage-req", "content": "stage", "timeout_ms": 2000}))
        task_message = await ws.receive_json()
        await ws.send_json({"type": "progress", "request_id": "stage-req", "stage": "USER_MESSAGE_CONFIRMED"})
        await asyncio.sleep(0.05)
        status = await self.session.get(self.base_url + "/api/tasks/stage-req", headers=token_headers)
        task_body = (await status.json())["task"]
        self.assertEqual(task_body["stage"], "USER_MESSAGE_CONFIRMED")
        await ws.send_json({"type": "result", "request_id": "stage-req", "conversation_id": "stage-conv", "message_id": "a1", "result": "done"})
        response = await send_task
        self.assertEqual((await response.json())["result"], "done")
        await ws.close()

    async def image_fixture(self):
        image = Path(self.temp_dir.name) / "sample.png"
        image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
        ws = await self.session.ws_connect(self.ws_url, headers={"Origin": "chrome-extension://fixture"})
        await ws.receive_json()
        await ws.send_json({"type": "hello", "tab_bound": True, "page_ready": True, "target_id": "vision", "tab_id": 30})
        await asyncio.sleep(0.01)
        return ws, {"image_path": str(image), "prompt": "describe", "target_id": "vision", "timeout_ms": 2000}

    async def post_image(self, payload):
        return await self.session.post(self.base_url + "/api/chat/send-image", headers={"X-Bridge-Token": self.token}, json=payload)

    async def test_image_duplicates_join_then_replay_from_storage(self):
        ws, payload = await self.image_fixture()
        first = asyncio.create_task(self.post_image(payload))
        task = await ws.receive_json()
        self.assertEqual(task["type"], "send_image")
        self.assertEqual(task["image_path"], payload["image_path"])
        self.assertNotIn("pasted", task)
        second = asyncio.create_task(self.post_image(payload))
        await asyncio.sleep(0.05)
        self.assertEqual(len(self.app[SERVICE_KEY].jobs), 1)
        await ws.send_json({"type": "result", "request_id": task["request_id"], "conversation_id": "vision-conv", "result": "one image"})
        bodies = [await (await first).json(), await (await second).json()]
        self.assertEqual(bodies[0]["request_id"], bodies[1]["request_id"])
        replay = await (await self.post_image(payload)).json()
        self.assertTrue(replay["deduplicated"])
        self.assertEqual(replay["result"], "one image")
        saved = self.app[SERVICE_KEY].store.get_task(task["request_id"])
        self.assertEqual(saved["state"], "completed")
        self.assertTrue(saved["fingerprint"])
        self.assertEqual(saved["conversation_id"], "vision-conv")
        self.assertEqual(replay["conversation_id"], "vision-conv")
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.receive_json(), 0.05)
        await ws.close()

    async def test_images_share_text_queue_and_cancel(self):
        ws, payload = await self.image_fixture()
        first = asyncio.create_task(self.session.post(self.base_url + "/api/chat/send", headers={"X-Bridge-Token": self.token}, json={"request_id": "text-first", "content": "hello", "target_id": "vision", "timeout_ms": 2000}))
        self.assertEqual((await ws.receive_json())["type"], "task")
        image = asyncio.create_task(self.post_image(payload))
        deadline = asyncio.get_running_loop().time() + 1
        while self.app[SERVICE_KEY].pending_queue_size() != 1 and asyncio.get_running_loop().time() < deadline:
            await asyncio.sleep(0.01)
        self.assertEqual(self.app[SERVICE_KEY].pending_queue_size(), 1)
        await ws.send_json({"type": "result", "request_id": "text-first", "result": "ok"})
        await first
        task = await ws.receive_json()
        cancel = await self.session.post(self.base_url + "/api/chat/cancel/" + task["request_id"], headers={"X-Bridge-Token": self.token})
        self.assertTrue((await cancel.json())["cancelled"])
        self.assertEqual((await ws.receive_json())["type"], "cancel")
        self.assertEqual((await (await image).json())["error"]["code"], "REQUEST_CANCELLED")
        self.assertEqual(self.app[SERVICE_KEY].store.get_task(task["request_id"])["state"], "cancelled")
        await ws.close()

    async def test_image_failure_is_not_redispatched_and_id_conflicts(self):
        ws, payload = await self.image_fixture()
        payload["request_id"] = "vision-explicit"
        first = asyncio.create_task(self.post_image(payload))
        task = await ws.receive_json()
        await ws.send_json({"type": "error", "request_id": task["request_id"], "code": "IMAGE_UPLOAD_TIMEOUT", "message": "not uploaded"})
        self.assertEqual((await (await first).json())["error"]["code"], "IMAGE_UPLOAD_TIMEOUT")
        self.assertEqual((await (await self.post_image(payload)).json())["error"]["code"], "IMAGE_UPLOAD_TIMEOUT")
        conflict = await self.post_image({**payload, "prompt": "different"})
        self.assertEqual(conflict.status, 409)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.receive_json(), 0.05)
        await ws.close()

    async def test_image_disconnect_is_recorded(self):
        ws, payload = await self.image_fixture()
        first = asyncio.create_task(self.post_image(payload))
        task = await ws.receive_json()
        await ws.close()
        self.assertEqual((await (await first).json())["error"]["code"], "EXTENSION_DISCONNECTED")
        await asyncio.sleep(0.02)
        self.assertEqual(self.app[SERVICE_KEY].store.get_task(task["request_id"])["state"], "failed")

    async def test_image_pause_and_invalid_timeout_do_not_dispatch(self):
        ws, payload = await self.image_fixture()
        self.app[SERVICE_KEY].paused = True
        self.assertEqual((await (await self.post_image(payload)).json())["error"]["code"], "PAUSED")
        invalid = await self.post_image({**payload, "timeout_ms": "invalid"})
        self.assertEqual((await invalid.json())["error"]["code"], "INVALID_REQUEST")
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(ws.receive_json(), 0.05)
        await ws.close()

    async def test_skip_paste_does_not_require_image_file(self):
        ws, payload = await self.image_fixture()
        first = asyncio.create_task(self.post_image({**payload, "image_path": "", "skip_paste": True}))
        task = await ws.receive_json()
        self.assertTrue(task["skip_paste"])
        self.assertEqual(task["image_path"], "")
        await ws.send_json({"type": "error", "request_id": task["request_id"], "code": "IMAGE_NOT_ATTACHED", "message": "no image"})
        self.assertEqual((await (await first).json())["error"]["code"], "IMAGE_NOT_ATTACHED")
        await ws.close()


if __name__ == "__main__":
    unittest.main()
