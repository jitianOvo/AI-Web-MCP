"""Local HTTP/WebSocket bridge for the Chromium extension."""

from __future__ import annotations

import asyncio
from collections import deque
import json
import logging
import time
import os
import uuid
import subprocess
from dataclasses import dataclass
from typing import Any

from aiohttp import WSMsgType, web

from . import __version__
from .config import load_config, resolve_project_path
from .protocol import make_message, new_request_id, text_hash
from .storage import Store
from .targets import TargetRegistry


class BridgeFailure(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class Job:
    request_id: str
    target_id: str
    conversation_id: str
    prompt: str
    expected_format: str
    timeout_ms: int
    future: asyncio.Future
    persona_id: str = ""
    task_group_id: str = ""
    cancelled: bool = False
    source_content: str = ""


def configure_logging(debug: bool) -> logging.Logger:
    logger = logging.getLogger("gpt_web_mcp")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(handler)
    return logger


class BridgeService:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.log = configure_logging(bool(config.get("debug")))
        self.store = Store(resolve_project_path(str(config.get("database_path", "data/gpt_web_mcp.sqlite3"))))
        self.queue: asyncio.Queue[Job] = asyncio.Queue(maxsize=int(config.get("max_queue_size", 20)))
        self.jobs: dict[str, Job] = {}
        self.targets = TargetRegistry()
        self.target_queues: dict[str, asyncio.Queue[Job]] = {}
        self.target_workers: dict[str, asyncio.Task] = {}
        self.active_semaphore = asyncio.Semaphore(max(1, int(config.get("max_active_jobs", 8))))
        self.rate_limit_lock = asyncio.Lock()
        self.dispatch_times: deque[float] = deque()
        self.extension_state: dict[str, Any] = {"connected": False, "tab_bound": False, "page_ready": False, "target_id": ""}
        self.current_job: Job | None = None
        self.active_jobs: dict[str, Job] = {}
        self.worker_task: asyncio.Task | None = None
        self.sync_waiters: dict[str, asyncio.Future] = {}
        self.bind_waiters: dict[str, asyncio.Future] = {}
        self.open_waiters: dict[str, asyncio.Future] = {}
        self.new_chat_waiters: dict[str, asyncio.Future] = {}
        self.state_waiters: dict[str, asyncio.Future] = {}
        self.image_waiters: dict[str, asyncio.Future] = {}
        self.paused = False
        self.last_request_id = ""
        self.last_success_time = 0.0
        self.last_error = ""
        self.last_input_diag: str = ""
        self.shutdown_event = asyncio.Event()

    def authorized(self, request: web.Request) -> bool:
        return request.headers.get("X-Bridge-Token", "") == str(self.config.get("bridge_token", ""))

    def status(self) -> dict[str, Any]:
        target_status = self.targets.status()
        default_target = self.targets.choose()
        if default_target:
            self.extension_state.update({
                "connected": True,
                "tab_bound": bool(default_target.state.get("tab_bound")),
                "page_ready": bool(default_target.state.get("page_ready")),
                "target_id": default_target.target_id,
                "input_ready": bool(default_target.state.get("input_ready", default_target.state.get("page_ready", False))),
            })
        elif self.targets.connections:
            first_target = next(iter(self.targets.connections.values()))
            self.extension_state.update({
                "connected": True,
                "tab_bound": bool(first_target.state.get("tab_bound")),
                "page_ready": bool(first_target.state.get("page_ready")),
                "target_id": first_target.target_id,
                "input_ready": bool(first_target.state.get("input_ready", first_target.state.get("page_ready", False))),
            })
        else:
            self.extension_state.update({"connected": False, "tab_bound": False, "page_ready": False, "target_id": ""})
        generating = any(bool(connection.state.get("generating")) for connection in self.targets.connections.values())
        response_state = "streaming" if generating else ("waiting" if self.active_jobs else "idle")
        return {
            "bridge": "online",
            "bridge_version": __version__,
            "protocol_version": "1.0",
            "extension": "connected" if self.extension_state["connected"] else "not_connected",
            "page": "ready" if self.extension_state["page_ready"] else "not_ready",
            "tab_bound": bool(self.extension_state["tab_bound"]),
            "target_id": self.extension_state.get("target_id", ""),
            "response_state": response_state,
            "paused": bool(self.paused),
            "mcp_running": True,
            "input_ready": bool(self.extension_state.get("input_ready", self.extension_state.get("page_ready", False))),
            "last_request_id": self.last_request_id,
            "last_success_time": self.last_success_time,
            "last_error": self.last_error,
            "input_diag": self.last_input_diag,
            "busy": bool(self.active_jobs),
            "active_jobs": len(self.active_jobs),
            "queue_size": self.pending_queue_size(),
            "targets": target_status,
            "chatgpt_tabs": self.chatgpt_tabs(),
        }

    def pending_queue_size(self) -> int:
        return self.queue.qsize() + sum(queue.qsize() for queue in self.target_queues.values())

    def chatgpt_tabs(self) -> list[dict[str, Any]]:
        """Merge tab snapshots reported by every extension socket into one list."""
        merged: dict[int, dict[str, Any]] = {}
        for connection in self.targets.connections.values():
            state = connection.state
            for tab in state.get("tabs") or []:
                tab_id = tab.get("tab_id")
                if tab_id is None:
                    continue
                entry = merged.setdefault(int(tab_id), {
                    "tab_id": int(tab_id),
                    "title": str(tab.get("tab_title", "")),
                    "url": str(tab.get("tab_url", "")),
                    "active": bool(tab.get("active")),
                    "window_id": tab.get("window_id"),
                    "bound_target_id": "",
                    "page_ready": False,
                    "generating": False,
                    "conversation_title": "",
                    "input_ready": False,
                    "is_new_chat": False,
                    "conversation_id": "",
                    "last_seen": state.get("updated_at", 0.0),
                })
                if state.get("tab_id") == tab_id:
                    entry["bound_target_id"] = connection.target_id
                    entry["page_ready"] = bool(state.get("page_ready"))
                    entry["generating"] = bool(state.get("generating"))
                    entry["conversation_title"] = str(state.get("conversation_title", ""))
                    entry["input_ready"] = bool(state.get("input_ready", state.get("page_ready", False)))
                    entry["is_new_chat"] = bool(state.get("is_new_chat"))
                    entry["conversation_id"] = str(state.get("conversation_id", ""))
        return list(merged.values())

    async def ensure_target_worker(self, target_id: str) -> None:
        if not target_id or target_id in self.target_workers:
            return
        queue = self.target_queues.setdefault(
            target_id,
            asyncio.Queue(maxsize=int(self.config.get("max_queue_size", 20))),
        )
        self.target_workers[target_id] = asyncio.create_task(
            self.target_worker(target_id, queue), name=f"gpt-web-mcp-target-{target_id}"
        )

    async def enqueue_job(self, job: Job) -> None:
        target = self.targets.get(job.target_id) if job.target_id else None
        if target and self.targets.is_ready(target):
            await self.ensure_target_worker(job.target_id)
            await self.target_queues[job.target_id].put(job)
            return
        await self.queue.put(job)

    async def wait_for_rate_limit(self) -> None:
        limit = int(self.config.get("rate_limit_per_minute", 0))
        if limit <= 0:
            return
        window = max(0.01, float(self.config.get("rate_limit_window_sec", 60)))
        while True:
            async with self.rate_limit_lock:
                now = time.monotonic()
                while self.dispatch_times and now - self.dispatch_times[0] >= window:
                    self.dispatch_times.popleft()
                if len(self.dispatch_times) < limit:
                    self.dispatch_times.append(now)
                    return
                wait_seconds = max(0.01, window - (now - self.dispatch_times[0]))
            await asyncio.sleep(wait_seconds)

    async def start(self, app: web.Application) -> None:
        self.worker_task = asyncio.create_task(self.worker(), name="gpt-web-mcp-worker")

    async def stop(self, app: web.Application) -> None:
        workers = [task for task in [self.worker_task, *self.target_workers.values()] if task]
        for task in workers:
            task.cancel()
        if workers:
            await asyncio.gather(*workers, return_exceptions=True)
        self.worker_task = None
        self.target_workers.clear()
        for connection in list(self.targets.connections.values()):
            if not connection.websocket.closed:
                await connection.websocket.close(code=1001, message=b"bridge shutdown")

    @staticmethod
    def error(code: str, message: str, status: int = 400, request_id: str = "") -> web.Response:
        return web.json_response({"success": False, "request_id": request_id, "error": {"code": code, "message": message}}, status=status)

    async def handle_status(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        return web.json_response({"success": True, "status": self.status()})

    async def handle_tabs(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        tabs = self.chatgpt_tabs()
        return web.json_response({"success": True, "tabs": tabs, "count": len(tabs)})

    async def handle_bind_tab(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        try:
            payload = await request.json()
        except Exception:
            return self.error("INVALID_JSON", "请求体必须是 JSON")
        try:
            tab_id = int(payload.get("tab_id"))
        except (TypeError, ValueError):
            return self.error("INVALID_TAB_ID", "tab_id 必须是整数")
        connection = self.targets.choose_control()
        if not connection or connection.websocket.closed:
            return self.error("EXTENSION_NOT_CONNECTED", "浏览器扩展尚未连接", 503)
        loop = asyncio.get_running_loop()
        request_id = str(payload.get("request_id") or new_request_id("bind"))
        waiter = loop.create_future()
        self.bind_waiters[request_id] = waiter
        await connection.websocket.send_json(make_message("bind_tab", request_id=request_id, tab_id=tab_id))
        try:
            result = await asyncio.wait_for(waiter, timeout=10)
            return web.json_response({
                "success": True, "request_id": request_id, "tab_id": tab_id,
                "target_id": str(result.get("target_id", "")), "title": str(result.get("title", "")),
            })
        except asyncio.TimeoutError:
            return self.error("BIND_TIMEOUT", "绑定标签页超时", 503, request_id)
        finally:
            self.bind_waiters.pop(request_id, None)

    async def handle_open_tab(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        connection = self.targets.choose_control()
        if not connection or connection.websocket.closed:
            return self.error("EXTENSION_NOT_CONNECTED", "浏览器扩展尚未连接", 503)
        loop = asyncio.get_running_loop()
        request_id = new_request_id("open")
        waiter = loop.create_future()
        self.open_waiters[request_id] = waiter
        await connection.websocket.send_json(make_message("open_tab", request_id=request_id))
        try:
            result = await asyncio.wait_for(waiter, timeout=45)
            return web.json_response({
                "success": True, "request_id": request_id,
                "tab_id": result.get("tab_id"), "target_id": str(result.get("target_id", "")),
                "ready": bool(result.get("ready")),
            })
        except asyncio.TimeoutError:
            return self.error("OPEN_TAB_TIMEOUT", "新建标签页超时", 503, request_id)
        finally:
            self.open_waiters.pop(request_id, None)

    async def handle_reload_extension(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        payload = await request.json() if request.can_read_body else {}
        target = self.targets.choose()
        tab_id = int(payload.get("tab_id") or (target.state.get("tab_id") if target else 0) or 0)
        live = [c for c in self.targets.connections.values() if not c.websocket.closed]
        if not live:
            return self.error("EXTENSION_NOT_CONNECTED", "浏览器扩展尚未连接", 503)
        for connection in live:
            await connection.websocket.send_json(make_message("reload_extension", request_id=new_request_id("reload"), tab_id=tab_id))
        return web.json_response({"success": True, "requested": True, "tab_id": tab_id})

    async def handle_new_chat(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        payload = await request.json() if request.can_read_body else {}
        requested_target = str(payload.get("target_id", ""))
        connection = self.targets.choose(requested_target)
        if not connection or connection.websocket.closed:
            return self.error("EXTENSION_NOT_CONNECTED", "浏览器扩展尚未连接", 503)
        loop = asyncio.get_running_loop()
        request_id = new_request_id("newchat")
        waiter = loop.create_future()
        self.new_chat_waiters[request_id] = waiter
        await connection.websocket.send_json(make_message("new_chat", request_id=request_id, target_id=connection.target_id))
        try:
            result = await asyncio.wait_for(waiter, timeout=30)
            return web.json_response({
                "success": True, "request_id": request_id,
                "conversation_id": str(result.get("conversation_id", "")),
                "is_new_chat": bool(result.get("is_new_chat")),
            })
        except asyncio.TimeoutError:
            return self.error("NEW_CHAT_TIMEOUT", "进入新聊天超时", 503, request_id)
        finally:
            self.new_chat_waiters.pop(request_id, None)

    async def handle_sync_state(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        payload = await request.json() if request.can_read_body else {}
        requested_target = str(payload.get("target_id", ""))
        connection = self.targets.choose(requested_target)
        if not connection or connection.websocket.closed:
            return self.error("EXTENSION_NOT_CONNECTED", "浏览器扩展尚未连接", 503)
        conversation_id = str(payload.get("conversation_id") or "current")
        sync = {
            "conversation_id": conversation_id, "messages": [],
            "user_message_on_screen": False, "assistant_present": False,
            "last_text": "", "generating": bool(connection.state.get("generating")),
            "page_ready": bool(connection.state.get("page_ready")), "input_ready": bool(connection.state.get("input_ready", connection.state.get("page_ready", False))),
            "is_new_chat": bool(connection.state.get("is_new_chat")), "error": "",
        }
        sync_request_id = new_request_id("sync")
        waiter = asyncio.get_running_loop().create_future()
        self.sync_waiters[sync_request_id] = waiter
        await connection.websocket.send_json(make_message("sync", request_id=sync_request_id, target_id=connection.target_id, conversation_id=conversation_id))
        try:
            sync_result = await asyncio.wait_for(waiter, timeout=15)
            sync["conversation_id"] = str(sync_result.get("conversation_id") or conversation_id)
            sync["messages"] = list(sync_result.get("messages") or [])
        except asyncio.TimeoutError:
            sync["error"] = "SYNC_TIMEOUT"
        finally:
            self.sync_waiters.pop(sync_request_id, None)
        state_request_id = new_request_id("state")
        state_waiter = asyncio.get_running_loop().create_future()
        self.state_waiters[state_request_id] = state_waiter
        await connection.websocket.send_json(make_message("check_state", request_id=state_request_id, target_id=connection.target_id, prompt=""))
        try:
            state_result = await asyncio.wait_for(state_waiter, timeout=8)
            for key in ("user_message_on_screen", "assistant_present", "last_text", "generating", "page_ready", "input_ready", "is_new_chat", "conversation_id", "input_text", "url", "dom", "dom_detail"):
                if key in state_result:
                    sync[key] = state_result[key]
        except asyncio.TimeoutError:
            if not sync["error"]:
                sync["error"] = "STATE_TIMEOUT"
        finally:
            self.state_waiters.pop(state_request_id, None)
        sync["success"] = not sync["error"]
        return web.json_response(sync)

    async def handle_pause(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        self.paused = True
        return web.json_response({"success": True, "paused": True})

    async def handle_resume(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        self.paused = False
        return web.json_response({"success": True, "paused": False})

    async def handle_latest(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        conversation_id = str(request.query.get("conversation_id", "current"))
        rows = self.store.search_messages(conversation_id=conversation_id, limit=1)
        message = rows[0] if rows else None
        conversation = self.store.get_conversation(conversation_id)
        generating = any(bool(connection.state.get("generating")) for connection in self.targets.connections.values())
        return web.json_response({
            "success": True,
            "conversation_id": conversation_id,
            "title": conversation["title"] if conversation else "",
            "message": message,
            "response_state": "streaming" if generating else "idle",
        })

    async def handle_shutdown(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        self.shutdown_event.set()
        return web.json_response({"success": True, "shutting_down": True})

    async def handle_send_image(self, request: web.Request) -> web.Response:
        """Ask the web ChatGPT to understand an image via the clipboard-paste path."""
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        try:
            payload = await request.json()
        except Exception:
            return self.error("INVALID_JSON", "请求体必须是 JSON")
        image_path = str(payload.get("image_path", "")).strip()
        skip_paste = bool(payload.get("skip_paste"))
        image_file = None
        if image_path:
            candidate = resolve_project_path(image_path)
            if not candidate.exists() or not candidate.is_file():
                return self.error("IMAGE_NOT_FOUND", f"图片不存在：{candidate}", 404)
            image_file = candidate
        elif not skip_paste:
            return self.error("INVALID_IMAGE", "image_path 不能为空")
        requested_target = str(payload.get("target_id", ""))
        connection = self.targets.choose(requested_target)
        if not connection or connection.websocket.closed:
            return self.error("EXTENSION_NOT_CONNECTED", "浏览器扩展尚未连接", 503)
        # System-level Ctrl+V (no CDP, works even when the window is background).
        # Let the extension bring the target window to the foreground and focus
        # the composer, then OS-level Ctrl+V pastes into the focused composer.
        if not skip_paste:
            try:
                await asyncio.to_thread(self._set_clipboard_image, image_file)
            except BridgeFailure as error:
                return self.error(error.code, error.message, 500)
        if not skip_paste:
            try:
                await connection.websocket.send_json(make_message(
                    "focus", request_id=new_request_id("imgfocus"), target_id=connection.target_id,
                ))
            except Exception:
                pass
            await asyncio.sleep(1.0)
            try:
                await asyncio.to_thread(self._paste_clipboard)
            except BridgeFailure as error:
                return self.error(error.code, error.message, 500)
        request_id = str(payload.get("request_id") or new_request_id("img"))
        waiter = asyncio.get_running_loop().create_future()
        self.image_waiters[request_id] = waiter
        timeout_ms = int(payload.get("timeout_ms", 600000))
        try:
            await connection.websocket.send_json(make_message(
                "send_image", request_id=request_id, target_id=connection.target_id,
                conversation_id=str(payload.get("conversation_id") or "current"),
                prompt=str(payload.get("prompt") or "请描述这张图片"),
                expected_format=str(payload.get("expected_format") or "text"),
                timeout_ms=timeout_ms,
                pasted=True,
            ))
            result = await asyncio.wait_for(waiter, timeout=timeout_ms / 1000 + 20)
            return web.json_response({"success": True, "request_id": request_id, **result})
        except asyncio.TimeoutError:
            return self.error("IMAGE_TIMEOUT", "图片询问超时", 503, request_id)
        except BridgeFailure as error:
            return self.error(error.code, error.message, 499, request_id)
        finally:
            self.image_waiters.pop(request_id, None)

    @staticmethod
    def _set_clipboard_image(image_file: Path) -> None:
        """Put the image onto the system clipboard via PowerShell (STA)."""
        image_file = image_file.resolve()
        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            f"$img=[System.Drawing.Image]::FromFile(\"{str(image_file).replace(chr(92), chr(92) + chr(92))}\"); "
            "$bmp=New-Object System.Drawing.Bitmap $img; "
            "[System.Windows.Forms.Clipboard]::SetImage($bmp); "
            "$img.Dispose(); $bmp.Dispose(); "
            "'clipboard-ok'"
        )
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-Command", script],
            capture_output=True, text=True, timeout=30,
        )
        if completed.returncode != 0 or "clipboard-ok" not in completed.stdout:
            detail = (completed.stderr or "").strip()[:300] or "PowerShell 设置剪贴板失败"
            raise BridgeFailure("CLIPBOARD_FAILED", detail)

    @staticmethod
    def _paste_clipboard() -> None:
        """System-level Ctrl+V via the native helper (paste-only, no Enter)."""
        helper = resolve_project_path(
            str(load_config().get("sendinput_helper", "build/gpt_sendinput.exe"))
        )
        if not helper.exists():
            raise BridgeFailure("SENDINPUT_MISSING", f"系统级粘贴助手不存在：{helper}")
        completed = subprocess.run(
            [str(helper), "--paste"], timeout=25,
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        if completed.returncode != 0:
            raise BridgeFailure("SENDINPUT_PASTE_FAILED", f"系统级粘贴失败 rc={completed.returncode}")

    async def handle_send(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        try:
            payload = await request.json()
        except Exception:
            return self.error("INVALID_JSON", "请求体必须是 JSON")
        content = str(payload.get("content", ""))
        if not content.strip():
            return self.error("EMPTY_CONTENT", "消息内容为空")
        if len(content) > int(self.config.get("max_text_chars", 200000)):
            return self.error("CONTENT_TOO_LARGE", "消息超过字符上限", 413)
        if self.pending_queue_size() >= int(self.config.get("max_queue_size", 20)):
            return self.error("QUEUE_FULL", "Bridge 队列已满", 429)
        if self.paused:
            return self.error("PAUSED", "Bridge 已暂停，暂不接受新任务", 503)
        loop = asyncio.get_running_loop()
        request_id = str(payload.get("request_id") or new_request_id())
        self.last_request_id = request_id
        conversation_id = str(payload.get("conversation_id") or "current")
        persona_id = str(payload.get("persona_id", ""))
        task_group_id = str(payload.get("task_group_id", ""))
        source_content = content
        try:
            content = self._apply_persona(content, persona_id)
        except BridgeFailure as error:
            return self.error(error.code, error.message, 404, request_id)
        requested_target_id = str(payload.get("target_id", ""))
        selected_target = self.targets.choose(requested_target_id)
        target_id = selected_target.target_id if selected_target else requested_target_id
        job = Job(
            request_id, target_id, conversation_id, content,
            str(payload.get("expected_format", "text")), int(payload.get("timeout_ms", 600000)),
            loop.create_future(), persona_id, task_group_id, False, source_content,
        )
        self.jobs[request_id] = job
        self.store.create_task(request_id, conversation_id, content, target_id=target_id, persona_id=persona_id, task_group_id=task_group_id)
        if task_group_id:
            self.store.create_task_group(task_group_id)
        await self.enqueue_job(job)
        try:
            result = await job.future
            self.last_success_time = time.time()
            return web.json_response({"success": True, "request_id": request_id, **result})
        except BridgeFailure as error:
            self.last_error = error.code
            return self.error(error.code, error.message, 499 if error.code == "REQUEST_CANCELLED" else 503, request_id)
        finally:
            self.jobs.pop(request_id, None)

    def _apply_persona(self, content: str, persona_id: str) -> str:
        if not persona_id:
            return content
        persona = self.store.get_persona(persona_id)
        if not persona:
            raise BridgeFailure("PERSONA_NOT_FOUND", f"人格不存在：{persona_id}")
        system_prompt = str(persona.get("system_prompt", "")).strip()
        if not system_prompt:
            return content
        return (
            "PERSONA INSTRUCTION\n"
            f"{system_prompt}\n"
            "PERSONA INSTRUCTION END\n\n"
            "USER TASK\n"
            f"{content}"
        )

    async def handle_personas(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        if request.method == "GET":
            return web.json_response({"success": True, "personas": self.store.list_personas()})
        try:
            payload = await request.json()
        except Exception:
            return self.error("INVALID_JSON", "请求体必须是 JSON")
        persona_id = str(payload.get("persona_id", "")).strip()
        name = str(payload.get("name", "")).strip()
        if not persona_id or not name:
            return self.error("INVALID_PERSONA", "persona_id 和 name 均不可为空")
        config_json = payload.get("config_json", "{}")
        if not isinstance(config_json, str):
            config_json = json.dumps(config_json, ensure_ascii=False)
        self.store.upsert_persona(persona_id, name, str(payload.get("system_prompt", "")), config_json)
        return web.json_response({"success": True, "persona": self.store.get_persona(persona_id)})

    async def handle_task_group(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        task_group_id = request.match_info["task_group_id"]
        group = self.store.get_task_group(task_group_id)
        if not group:
            return self.error("TASK_GROUP_NOT_FOUND", "任务组不存在", 404)
        return web.json_response({"success": True, "task_group": group})

    async def handle_task_status(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        request_id = request.match_info["request_id"]
        task = self.store.get_task(request_id)
        if not task:
            return self.error("TASK_NOT_FOUND", "任务不存在", 404, request_id)
        return web.json_response({"success": True, "task": task})

    async def handle_task_group_submit(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        try:
            payload = await request.json()
        except Exception:
            return self.error("INVALID_JSON", "请求体必须是 JSON")
        task_group_id = str(request.match_info["task_group_id"] or payload.get("task_group_id") or new_request_id("group"))
        title = str(payload.get("title", ""))
        tasks = payload.get("tasks")
        if not isinstance(tasks, list) or not tasks:
            return self.error("EMPTY_TASK_GROUP", "tasks 必须是非空数组")
        if len(tasks) > 32:
            return self.error("TASK_GROUP_TOO_LARGE", "单个任务组最多 32 项")
        if self.pending_queue_size() + len(tasks) > int(self.config.get("max_queue_size", 20)):
            return self.error("QUEUE_FULL", "Bridge 队列无法容纳整个任务组", 429, task_group_id)
        self.store.create_task_group(task_group_id, title)
        self.store.update_task_group(task_group_id, "running")
        loop = asyncio.get_running_loop()
        jobs: list[Job] = []
        prepared: list[tuple[str, str, str, str, str, int, str, str]] = []
        try:
            for index, item in enumerate(tasks):
                if not isinstance(item, dict):
                    raise BridgeFailure("INVALID_TASK", f"第 {index + 1} 项不是对象")
                content = str(item.get("content", ""))
                if not content.strip():
                    raise BridgeFailure("EMPTY_CONTENT", f"第 {index + 1} 项消息内容为空")
                if len(content) > int(self.config.get("max_text_chars", 200000)):
                    raise BridgeFailure("CONTENT_TOO_LARGE", f"第 {index + 1} 项超过字符上限")
                persona_id = str(item.get("persona_id", ""))
                source_content = content
                content = self._apply_persona(content, persona_id)
                requested_target_id = str(item.get("target_id", ""))
                selected_target = self.targets.choose(requested_target_id)
                target_id = selected_target.target_id if selected_target else requested_target_id
                request_id = str(item.get("request_id") or f"{task_group_id}_{index + 1}_{uuid.uuid4().hex[:8]}")
                conversation_id = str(item.get("conversation_id") or "current")
                prepared.append((request_id, target_id, conversation_id, content, persona_id, int(item.get("timeout_ms", 600000)), str(item.get("expected_format", "text")), source_content))
            for request_id, target_id, conversation_id, content, persona_id, timeout_ms, expected_format, source_content in prepared:
                job = Job(
                    request_id, target_id, conversation_id, content,
                    expected_format, timeout_ms,
                    loop.create_future(), persona_id, task_group_id, False, source_content,
                )
                self.jobs[request_id] = job
                self.store.create_task(request_id, conversation_id, content, target_id=target_id, persona_id=persona_id, task_group_id=task_group_id)
                jobs.append(job)
                await self.enqueue_job(job)
        except BridgeFailure as error:
            self.store.update_task_group(task_group_id, "failed")
            return self.error(error.code, error.message, 400, task_group_id)

        results: list[dict[str, Any]] = []
        for job in jobs:
            try:
                result = await job.future
                results.append({"request_id": job.request_id, "persona_id": job.persona_id, "target_id": job.target_id, "success": True, **result})
            except BridgeFailure as error:
                results.append({"request_id": job.request_id, "persona_id": job.persona_id, "target_id": job.target_id, "success": False, "error": {"code": error.code, "message": error.message}})
            finally:
                self.jobs.pop(job.request_id, None)
        state = "completed" if all(item["success"] for item in results) else "partial_failure"
        self.store.update_task_group(task_group_id, state)
        successful = [item for item in results if item["success"]]
        source_groups: dict[str, list[dict[str, Any]]] = {}
        for job, item in zip(jobs, results):
            if item["success"]:
                source_groups.setdefault(job.source_content.strip(), []).append(item)
        conflict_candidates = []
        for source, items in source_groups.items():
            distinct = {str(item.get("result", "")).strip() for item in items}
            if len(items) > 1 and len(distinct) > 1:
                conflict_candidates.append({
                    "source_content": source,
                    "request_ids": [item["request_id"] for item in items],
                    "results": [item.get("result", "") for item in items],
                })
        merged_lines = [f"# 任务组汇总：{title or task_group_id}", ""]
        for item in successful:
            merged_lines.extend([
                f"## {item.get('persona_id') or 'default'} · {item.get('target_id') or 'default'}",
                "",
                str(item.get("result", "")),
                "",
            ])
        return web.json_response({
            "success": True,
            "task_group_id": task_group_id,
            "state": state,
            "results": results,
            "merged_markdown": "\n".join(merged_lines),
            "conflict_candidates": conflict_candidates,
        })

    async def handle_messages(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        conversation_id = str(request.query.get("conversation_id", "current"))
        try:
            after = int(request.query.get("after", "0"))
            limit = int(request.query.get("limit", "100"))
        except ValueError:
            return self.error("INVALID_CURSOR", "游标必须是整数")
        return web.json_response({"success": True, "conversation_id": conversation_id, "messages": self.store.list_messages(conversation_id, after, limit)})

    async def handle_wait_event(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        conversation_id = str(request.query.get("conversation_id", "current"))
        try:
            after = int(request.query.get("after", "0"))
            timeout_ms = max(0, min(120000, int(request.query.get("timeout_ms", "30000"))))
        except ValueError:
            return self.error("INVALID_WAIT", "after 和 timeout_ms 必须是整数")
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        messages = self.store.list_messages(conversation_id, after, 100)
        while not messages and asyncio.get_running_loop().time() < deadline:
            remaining = deadline - asyncio.get_running_loop().time()
            await asyncio.sleep(min(0.25, max(0.001, remaining)))
            messages = self.store.list_messages(conversation_id, after, 100)
        return web.json_response({
            "success": True,
            "conversation_id": conversation_id,
            "messages": messages,
            "timed_out": not bool(messages),
        })

    async def handle_search(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        limit_value = request.query.get("limit", "100")
        try:
            limit = int(limit_value)
        except ValueError:
            return self.error("INVALID_LIMIT", "limit 必须是整数")
        conversation_id = str(request.query.get("conversation_id", ""))
        query = str(request.query.get("q", ""))
        role = str(request.query.get("role", ""))
        return web.json_response({
            "success": True,
            "conversation_id": conversation_id,
            "query": query,
            "role": role,
            "messages": self.store.search_messages(conversation_id, query, role, limit),
        })

    async def handle_export(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        conversation_id = str(request.query.get("conversation_id", ""))
        output_format = str(request.query.get("format", "markdown")).lower()
        if output_format not in {"markdown", "json"}:
            return self.error("INVALID_EXPORT_FORMAT", "format 只支持 markdown 或 json")
        messages = self.store.list_messages(conversation_id, 0, 1000) if conversation_id else list(reversed(self.store.search_messages(limit=1000)))
        if output_format == "json":
            content = json.dumps(messages, ensure_ascii=False, indent=2)
            content_type = "application/json; charset=utf-8"
        else:
            lines = [f"# ChatGPT 对话：{conversation_id or '全部消息'}", ""]
            for message in messages:
                lines.extend([
                    f"## {message['role']} · {message['message_id']}",
                    "",
                    message["content"],
                    "",
                ])
            content = "\n".join(lines)
            content_type = "text/markdown; charset=utf-8"
        return web.json_response({"success": True, "conversation_id": conversation_id, "format": output_format, "content": content, "content_type": content_type})

    async def handle_sync(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        payload = await request.json() if request.can_read_body else {}
        requested_target_id = str(payload.get("target_id", ""))
        target = self.targets.choose(requested_target_id)
        if not target:
            return self.error("EXTENSION_NOT_CONNECTED", "浏览器扩展尚未连接", 503)
        request_id = str(payload.get("request_id") or new_request_id("sync"))
        conversation_id = str(payload.get("conversation_id") or "current")
        waiter = asyncio.get_running_loop().create_future()
        self.sync_waiters[request_id] = waiter
        await target.websocket.send_json(make_message("sync", request_id=request_id, target_id=target.target_id, conversation_id=conversation_id))
        try:
            sync_result = await asyncio.wait_for(waiter, timeout=30)
            actual_conversation_id = str(sync_result.get("conversation_id") or conversation_id)
            messages = list(sync_result.get("messages") or [])
            for message in messages:
                role = str(message.get("role", "assistant"))
                content = str(message.get("content", ""))
                if not content.strip():
                    continue
                self.store.upsert_conversation(actual_conversation_id, target.target_id)
                self.store.append_message(actual_conversation_id, str(message.get("message_id", uuid.uuid4().hex)), role, content, str(message.get("content_hash") or text_hash(role, content)))
            return web.json_response({"success": True, "request_id": request_id, "conversation_id": actual_conversation_id, "messages": self.store.list_messages(actual_conversation_id, 0, 1000)})
        except asyncio.TimeoutError:
            return self.error("SYNC_TIMEOUT", "页面同步超时", 503, request_id)
        finally:
            self.sync_waiters.pop(request_id, None)

    async def handle_cancel(self, request: web.Request) -> web.Response:
        if not self.authorized(request):
            return self.error("UNAUTHORIZED", "Bridge token 不正确", 401)
        request_id = request.match_info["request_id"]
        job = self.jobs.get(request_id)
        if not job:
            return self.error("REQUEST_NOT_FOUND", "请求不存在", 404, request_id)
        job.cancelled = True
        target = self.targets.choose(job.target_id, ready_only=False)
        if target and not target.websocket.closed:
            await target.websocket.send_json(make_message("cancel", request_id=request_id, target_id=job.target_id))
        if not job.future.done():
            job.future.set_exception(BridgeFailure("REQUEST_CANCELLED", "请求已取消"))
        return web.json_response({"success": True, "request_id": request_id, "cancelled": True})

    async def handle_extension(self, request: web.Request) -> web.StreamResponse:
        if not request.headers.get("Origin", "").startswith("chrome-extension://"):
            return self.error("INVALID_EXTENSION_ORIGIN", "只接受 Chromium 扩展连接", 403)
        if request.query.get("token", "") != str(self.config.get("bridge_token", "")):
            return self.error("UNAUTHORIZED", "Extension token 不正确", 401)
        ws = web.WebSocketResponse(heartbeat=20)
        await ws.prepare(request)
        connection_id = uuid.uuid4().hex
        self.targets.attach(connection_id, ws)
        await ws.send_json(make_message("bridge_ready", status=self.status()))
        try:
            async for message in ws:
                if message.type == WSMsgType.TEXT:
                    try:
                        await self.handle_extension_message(json.loads(message.data), connection_id)
                    except json.JSONDecodeError:
                        self.log.warning("invalid extension JSON")
        finally:
            removed = self.targets.remove(connection_id)
            if removed and removed.target_id:
                active = self.active_jobs.get(removed.target_id)
                if active and not active.future.done():
                    active.future.set_exception(BridgeFailure("EXTENSION_DISCONNECTED", "目标浏览器扩展连接已断开"))
            if not self.targets.connections:
                self.extension_state.update({"connected": False, "tab_bound": False, "page_ready": False, "target_id": ""})
            if removed and removed.target_id and self.targets.get(removed.target_id) is None:
                worker = self.target_workers.pop(removed.target_id, None)
                queue = self.target_queues.pop(removed.target_id, None)
                if queue:
                    while not queue.empty():
                        queued_job = queue.get_nowait()
                        queued_job.cancelled = True
                        self.store.update_task(queued_job.request_id, "failed", error_code="EXTENSION_DISCONNECTED", error_message="目标浏览器扩展连接已断开")
                        if not queued_job.future.done():
                            queued_job.future.set_exception(BridgeFailure("EXTENSION_DISCONNECTED", "目标浏览器扩展连接已断开"))
                        queue.task_done()
                if worker:
                    worker.cancel()
        return ws

    async def handle_extension_message(self, data: dict[str, Any], connection_id: str = "") -> None:
        kind = data.get("type")
        if kind in {"hello", "status"} and bool(self.config.get("debug")):
            self.log.debug("ext %s conn=%s payload=%s", kind, connection_id, json.dumps(data, ensure_ascii=False)[:800])
        connection = self.targets.update(connection_id, data) if kind in {"hello", "status"} else self.targets.connections.get(connection_id)
        if kind in {"hello", "status"}:
            if connection is None:
                return
            self.extension_state.update({
                "connected": True,
                "tab_bound": bool(data.get("tab_bound")),
                "page_ready": bool(data.get("page_ready")),
                "target_id": connection.target_id,
                "input_ready": bool(data.get("input_ready", data.get("page_ready", False))),
            })
            browser_name = str(data.get("browser", "chromium"))
            browser_version = str(data.get("browser_version", ""))
            browser = f"{browser_name}/{browser_version}" if browser_version else browser_name
            self.store.upsert_target(connection.target_id, browser, data.get("tab_id"), str(data.get("tab_title", "")), str(data.get("tab_url", "")), bool(data.get("page_ready")))
            await self.ensure_target_worker(connection.target_id)
            return
        request_id = str(data.get("request_id", ""))
        if kind == "message_event":
            message = data.get("message") or {}
            conversation_id = str(data.get("conversation_id") or "current")
            role = str(message.get("role", "assistant"))
            content = str(message.get("content", ""))
            if content.strip():
                target_id = connection.target_id if connection else self.extension_state.get("target_id", "bound-tab")
                self.store.upsert_conversation(conversation_id, target_id, str(data.get("tab_title", "")), str(data.get("tab_url", "")))
                self.store.append_message(conversation_id, str(message.get("message_id", uuid.uuid4().hex)), role, content, str(message.get("content_hash") or text_hash(role, content)))
            return
        if kind == "sync_result":
            waiter = self.sync_waiters.get(str(data.get("request_id", "")))
            if waiter and not waiter.done():
                waiter.set_result({
                    "conversation_id": str(data.get("conversation_id") or "current"),
                    "messages": list(data.get("messages") or []),
                })
            return
        if kind == "error" and request_id in self.sync_waiters:
            waiter = self.sync_waiters[request_id]
            if not waiter.done():
                waiter.set_exception(BridgeFailure(str(data.get("code", "SYNC_FAILED")), str(data.get("message", "页面同步失败"))))
            return
        if kind == "bound_result":
            waiter = self.bind_waiters.get(request_id)
            if waiter and not waiter.done():
                waiter.set_result({
                    "target_id": str(data.get("target_id", "")),
                    "title": str(data.get("title", "")),
                })
            return
        if kind == "error" and request_id in self.bind_waiters:
            waiter = self.bind_waiters[request_id]
            if not waiter.done():
                waiter.set_exception(BridgeFailure(str(data.get("code", "BIND_FAILED")), str(data.get("message", "绑定标签页失败"))))
            return
        if kind == "progress":
            stage = str(data.get("stage", ""))
            if stage and request_id in self.jobs:
                self.store.update_task(request_id, "running", stage=stage)
            if stage == "INPUT_SENT" and data.get("detail"):
                self.last_input_diag = str(data.get("detail"))
            return
        if kind == "open_result":
            waiter = self.open_waiters.get(request_id)
            if waiter and not waiter.done():
                waiter.set_result({
                    "tab_id": data.get("tab_id"), "target_id": str(data.get("target_id", "")), "ready": bool(data.get("ready")),
                })
            return
        if kind == "new_chat_result":
            waiter = self.new_chat_waiters.get(request_id)
            if waiter and not waiter.done():
                waiter.set_result({
                    "conversation_id": str(data.get("conversation_id", "")), "is_new_chat": bool(data.get("is_new_chat")),
                })
            return
        if kind == "state_result":
            waiter = self.state_waiters.get(request_id)
            if waiter and not waiter.done():
                waiter.set_result(dict(data.get("state") or {}))
            return
        if kind == "error":
            for waiters in (self.open_waiters, self.new_chat_waiters, self.state_waiters):
                waiter = waiters.get(request_id)
                if waiter and not waiter.done():
                    waiter.set_exception(BridgeFailure(str(data.get("code", "EXTENSION_ERROR")), str(data.get("message", "扩展执行失败"))))
        if request_id in self.image_waiters:
            waiter = self.image_waiters[request_id]
            if waiter and not waiter.done():
                if kind == "result":
                    result = str(data.get("result", ""))
                    if result.strip():
                        conversation_id = str(data.get("conversation_id") or "current")
                        self.store.upsert_conversation(conversation_id, connection.target_id if connection else "")
                        self.store.append_message(conversation_id, str(data.get("message_id", uuid.uuid4().hex)), "assistant", result, text_hash("assistant", result))
                        waiter.set_result({"result": result, "conversation_id": conversation_id})
                    else:
                        waiter.set_exception(BridgeFailure("EMPTY_RESPONSE", "ChatGPT 返回空内容"))
                elif kind == "error":
                    waiter.set_exception(BridgeFailure(str(data.get("code", "EXTENSION_ERROR")), str(data.get("message", "扩展执行失败"))))
            return
        job = self.jobs.get(request_id)
        if not job or job.future.done():
            return
        if connection and job.target_id != connection.target_id:
            return
        if kind == "result":
            result = str(data.get("result", ""))
            if result.strip():
                conversation_id = str(data.get("conversation_id") or job.conversation_id)
                job.conversation_id = conversation_id
                self.store.update_task(request_id, "completed", result=result)
                self.store.upsert_conversation(conversation_id, job.target_id)
                self.store.append_message(conversation_id, str(data.get("message_id", uuid.uuid4().hex)), "assistant", result, text_hash("assistant", result))
                job.future.set_result({"result": result, "conversation_id": conversation_id})
            else:
                self.store.update_task(request_id, "failed", error_code="EMPTY_RESPONSE", error_message="ChatGPT 返回空内容")
                job.future.set_exception(BridgeFailure("EMPTY_RESPONSE", "ChatGPT 返回空内容"))
        elif kind == "error":
            code = str(data.get("code", "EXTENSION_ERROR"))
            detail = str(data.get("message", "扩展执行失败"))
            if code in {"DEBUGGER_BUSY", "CDP_FAILED"}:
                try:
                    if await self._run_sendinput(job.prompt):
                        await connection.websocket.send_json(make_message(
                            "task", request_id=job.request_id, target_id=job.target_id,
                            conversation_id=job.conversation_id, prompt=job.prompt,
                            expected_format=job.expected_format, timeout_ms=job.timeout_ms,
                            persona_id=job.persona_id, task_group_id=job.task_group_id,
                            input_backend="verify",
                        ))
                        return
                except Exception:
                    pass
            self.store.update_task(request_id, "failed", error_code=code, error_message=detail)
            job.future.set_exception(BridgeFailure(code, detail))

    async def _run_sendinput(self, prompt: str) -> bool:
        """Win32 SendInput fallback: paste prompt via the native helper and press Enter."""
        helper = resolve_project_path(str(self.config.get("sendinput_helper", "build/gpt_sendinput.exe")))
        if not helper.exists():
            self.log.warning("sendinput helper missing: %s", helper)
            return False
        payload = resolve_project_path("tmp") / "sendinput_prompt.txt"
        payload.parent.mkdir(parents=True, exist_ok=True)
        payload.write_text(prompt, encoding="utf-8")
        try:
            result = subprocess.run(
                [str(helper), str(payload)], timeout=25,
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0),
            )
            return result.returncode == 0
        except Exception as error:
            self.log.warning("sendinput helper failed: %s", error)
            return False

    async def _classify_timeout(self, job: Job, target: Any) -> dict[str, Any]:
        """After a wait timeout, ask the page what actually happened."""
        base = {
            "classification": "state_unreachable", "user_message_on_screen": False,
            "assistant_present": False, "last_text": "", "generating": False,
            "page_ready": False, "input_ready": False, "conversation_id": "", "error": "",
        }
        if not target or target.websocket.closed:
            base["classification"] = "extension_offline"
            return base
        state_request_id = new_request_id("state")
        waiter = asyncio.get_running_loop().create_future()
        self.state_waiters[state_request_id] = waiter
        try:
            await target.websocket.send_json(make_message(
                "check_state", request_id=state_request_id, target_id=job.target_id, prompt=job.prompt,
            ))
            state = await asyncio.wait_for(waiter, timeout=8)
        except asyncio.TimeoutError:
            base["error"] = "STATE_TIMEOUT"
            return base
        except Exception:
            base["classification"] = "extension_offline"
            return base
        finally:
            self.state_waiters.pop(state_request_id, None)
        user_on = bool(state.get("user_message_on_screen"))
        assistant = bool(state.get("assistant_present"))
        generating = bool(state.get("generating"))
        last_text = str(state.get("last_text", ""))
        if not user_on:
            classification = "send_failed"
        elif generating:
            classification = "still_generating"
        elif assistant and last_text.strip():
            classification = "completed_but_missed"
        else:
            classification = "confirmed_no_reply"
        base.update(state)
        base["classification"] = classification
        return base

    async def worker(self) -> None:
        while True:
            job = await self.queue.get()
            try:
                async with self.active_semaphore:
                    await self.process_job(job)
            finally:
                self.queue.task_done()

    async def target_worker(self, target_id: str, queue: asyncio.Queue[Job]) -> None:
        while True:
            job = await queue.get()
            try:
                async with self.active_semaphore:
                    await self.process_job(job)
            finally:
                queue.task_done()

    async def process_job(self, job: Job) -> None:
        self.current_job = job
        self.active_jobs[job.target_id] = job
        self.store.update_task(job.request_id, "running")
        try:
            if job.cancelled:
                raise BridgeFailure("REQUEST_CANCELLED", "请求已取消")
            target = self.targets.choose(job.target_id)
            if not target:
                raise BridgeFailure("EXTENSION_NOT_CONNECTED", "浏览器扩展尚未连接")
            await self.wait_for_rate_limit()
            input_backend = str(self.config.get("input_backend", "cdp"))
            if input_backend == "sendinput":
                try:
                    await target.websocket.send_json(make_message("focus", target_id=job.target_id))
                except Exception:
                    pass
                await asyncio.sleep(0.4)
                if not await self._run_sendinput(job.prompt):
                    raise BridgeFailure("SENDINPUT_FAILED", "系统级输入助手未找到浏览器窗口或输入失败")
                input_backend = "verify"
            await target.websocket.send_json(make_message(
                "task", request_id=job.request_id, target_id=job.target_id,
                conversation_id=job.conversation_id, prompt=job.prompt,
                expected_format=job.expected_format, timeout_ms=job.timeout_ms,
                persona_id=job.persona_id, task_group_id=job.task_group_id,
                input_backend=input_backend,
            ))
            self.store.update_task(job.request_id, "running", stage="SUBMITTED")
            grace_ms = max(0, int(self.config.get("timeout_grace_ms", 5000)))
            result = await asyncio.wait_for(
                asyncio.shield(job.future),
                timeout=job.timeout_ms / 1000 + grace_ms / 1000,
            )
            if not job.future.done():
                job.future.set_result(result)
        except asyncio.TimeoutError:
            target = self.targets.choose(job.target_id, ready_only=False)
            if target and not target.websocket.closed:
                try:
                    await target.websocket.send_json(make_message("cancel", request_id=job.request_id, target_id=job.target_id))
                except (ConnectionError, RuntimeError):
                    pass
            checklist = await self._classify_timeout(job, target)
            classification = str(checklist.get("classification", "timeout"))
            last_text = str(checklist.get("last_text", ""))
            if classification == "completed_but_missed" and last_text.strip():
                conversation_id = str(checklist.get("conversation_id") or job.conversation_id)
                self.store.update_task(job.request_id, "completed", result=last_text, stage="COMPLETED")
                self.store.upsert_conversation(conversation_id, job.target_id)
                self.store.append_message(conversation_id, uuid.uuid4().hex, "assistant", last_text, text_hash("assistant", last_text))
                if not job.future.done():
                    job.future.set_result({"result": last_text, "conversation_id": conversation_id, "recovered": True, "classification": classification})
                return
            code_map = {
                "extension_offline": "EXTENSION_OFFLINE", "send_failed": "SEND_FAILED",
                "state_unreachable": "RESPONSE_TIMEOUT", "still_generating": "RESPONSE_TIMEOUT", "confirmed_no_reply": "RESPONSE_TIMEOUT",
            }
            code = code_map.get(classification, "RESPONSE_TIMEOUT")
            detail = f"等待回答超时，页面状态分类={classification}，user_on_screen={checklist.get('user_message_on_screen')}"
            self.store.update_task(job.request_id, "failed", error_code=code, error_message=detail)
            if not job.future.done():
                job.future.set_exception(BridgeFailure(code, detail))
        except BridgeFailure as error:
            self.store.update_task(job.request_id, "failed", error_code=error.code, error_message=error.message)
            if not job.future.done():
                job.future.set_exception(error)
        except Exception as error:
            self.log.exception("bridge worker crashed")
            if not job.future.done():
                job.future.set_exception(BridgeFailure("BRIDGE_INTERNAL_ERROR", str(error)))
        finally:
            if self.active_jobs.get(job.target_id) is job:
                self.active_jobs.pop(job.target_id, None)
            if self.current_job is job:
                self.current_job = None


SERVICE_KEY = web.AppKey("service", BridgeService)


def create_app(config: dict[str, Any] | None = None) -> web.Application:
    cfg = config or load_config()
    if cfg.get("host") not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("Bridge 只允许监听本机回环地址")
    service = BridgeService(cfg)
    app = web.Application()
    app[SERVICE_KEY] = service
    app.router.add_get("/api/status", service.handle_status)
    app.router.add_get("/api/tabs", service.handle_tabs)
    app.router.add_post("/api/tabs/bind", service.handle_bind_tab)
    app.router.add_post("/api/tabs/open", service.handle_open_tab)
    app.router.add_post("/api/reload-extension", service.handle_reload_extension)
    app.router.add_post("/api/shutdown", service.handle_shutdown)
    app.router.add_get("/api/personas", service.handle_personas)
    app.router.add_post("/api/personas", service.handle_personas)
    app.router.add_post("/api/chat/send", service.handle_send)
    app.router.add_post("/api/chat/send-image", service.handle_send_image)
    app.router.add_post("/api/chat/new", service.handle_new_chat)
    app.router.add_post("/api/chat/sync-state", service.handle_sync_state)
    app.router.add_post("/api/pause", service.handle_pause)
    app.router.add_post("/api/resume", service.handle_resume)
    app.router.add_get("/api/chat/latest", service.handle_latest)
    app.router.add_get("/api/chat/messages", service.handle_messages)
    app.router.add_get("/api/chat/search", service.handle_search)
    app.router.add_get("/api/chat/export", service.handle_export)
    app.router.add_get("/api/chat/wait", service.handle_wait_event)
    app.router.add_post("/api/chat/sync", service.handle_sync)
    app.router.add_post("/api/chat/cancel/{request_id}", service.handle_cancel)
    app.router.add_get("/api/task-groups/{task_group_id}", service.handle_task_group)
    app.router.add_post("/api/task-groups/{task_group_id}/submit", service.handle_task_group_submit)
    app.router.add_get("/api/tasks/{request_id}", service.handle_task_status)
    app.router.add_get("/ws/extension", service.handle_extension)
    app.on_startup.append(service.start)
    app.on_cleanup.append(service.stop)
    return app


async def serve() -> None:
    cfg = load_config()
    app = create_app(cfg)
    runner = web.AppRunner(app, access_log=None)
    await runner.setup()
    site = web.TCPSite(runner, cfg["host"], int(cfg["port"]))
    await site.start()
    print(f"GPT Web MCP Bridge: http://{cfg['host']}:{cfg['port']}", flush=True)
    try:
        await app[SERVICE_KEY].shutdown_event.wait()
    finally:
        await runner.cleanup()


def main() -> None:
    try:
        asyncio.run(serve())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
