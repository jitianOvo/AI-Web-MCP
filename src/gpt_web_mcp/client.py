"""Local HTTP client used by the MCP facade."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from .config import PROJECT_ROOT, load_config


_START_LOCK = threading.Lock()


class BridgeError(RuntimeError):
    def __init__(self, code: str, message: str, request_id: str = ""):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.request_id = request_id


class BridgeClient:
    def __init__(self, timeout: float | None = None):
        self.cfg = load_config()
        self.base_url = f"http://{self.cfg['host']}:{self.cfg['port']}"
        self.token = str(self.cfg["bridge_token"])
        self.timeout = timeout or float(self.cfg.get("response_timeout", 600)) + 15

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None, timeout: float | None = None) -> dict[str, Any]:
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            self.base_url + path,
            data=body,
            method=method,
            headers={"Content-Type": "application/json; charset=utf-8", "X-Bridge-Token": self.token},
        )
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=timeout or self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                result = json.loads(error.read().decode("utf-8"))
            except Exception:
                result = {"error": {"code": "BRIDGE_HTTP_ERROR", "message": str(error)}}
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            raise BridgeError("BRIDGE_OFFLINE", f"本地 Bridge 未响应：{error}") from error
        if not result.get("success", False):
            detail = result.get("error") or {}
            raise BridgeError(str(detail.get("code", "BRIDGE_ERROR")), str(detail.get("message", "Bridge 请求失败")), str(result.get("request_id", "")))
        return result

    def status(self) -> dict[str, Any]:
        return self._request("GET", "/api/status", timeout=3).get("status", {})

    def tabs(self) -> dict[str, Any]:
        return self._request("GET", "/api/tabs")

    def bind_tab(self, tab_id: int) -> dict[str, Any]:
        return self._request("POST", "/api/tabs/bind", {"tab_id": int(tab_id)}, timeout=15)

    def bound_tab(self) -> dict[str, Any]:
        tabs = self.tabs().get("tabs", [])
        bound = next((item for item in tabs if item.get("bound_target_id")), None)
        return bound or {"tab_id": None, "bound_target_id": "", "title": "", "url": ""}

    def latest_message(self, conversation_id: str = "current") -> dict[str, Any]:
        return self._request("GET", f"/api/chat/latest?conversation_id={urllib.parse.quote(conversation_id)}")

    def open_tab(self) -> dict[str, Any]:
        return self._request("POST", "/api/tabs/open", {}, timeout=50)

    def reload_extension(self, tab_id: int = 0) -> dict[str, Any]:
        return self._request("POST", "/api/reload-extension", {"tab_id": int(tab_id)}, timeout=5)

    def new_chat(self, target_id: str = "") -> dict[str, Any]:
        return self._request("POST", "/api/chat/new", {"target_id": target_id}, timeout=35)

    def sync_state(self, conversation_id: str = "current", target_id: str = "") -> dict[str, Any]:
        return self._request("POST", "/api/chat/sync-state", {"conversation_id": conversation_id, "target_id": target_id}, timeout=35)

    def pause(self) -> dict[str, Any]:
        return self._request("POST", "/api/pause", {}, timeout=5)

    def resume(self) -> dict[str, Any]:
        return self._request("POST", "/api/resume", {}, timeout=5)

    def wait_for_response(self, request_id: str, timeout_ms: int = 120000) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_ms / 1000
        while time.monotonic() < deadline:
            task = self.task_status(request_id)
            state = str(task.get("task", {}).get("state", ""))
            if state in {"completed", "failed", "cancelled", "interrupted"}:
                return task
            time.sleep(0.5)
        return {"success": True, "request_id": request_id, "timed_out": True}

    def shutdown(self) -> dict[str, Any]:
        return self._request("POST", "/api/shutdown", timeout=5)

    def ensure_running(self, wait_seconds: float = 10) -> dict[str, Any]:
        try:
            return self.status()
        except BridgeError as error:
            if error.code != "BRIDGE_OFFLINE":
                raise
        with _START_LOCK:
            try:
                return self.status()
            except BridgeError as error:
                if error.code != "BRIDGE_OFFLINE":
                    raise
            environment = os.environ.copy()
            source_path = str(PROJECT_ROOT / "src")
            environment["PYTHONPATH"] = source_path + os.pathsep + environment.get("PYTHONPATH", "")
            subprocess.Popen(
                [sys.executable, "-m", "gpt_web_mcp.bridge"],
                cwd=str(PROJECT_ROOT), stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                env=environment,
                creationflags=(getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0),
            )
            deadline = time.monotonic() + wait_seconds
            while time.monotonic() < deadline:
                time.sleep(0.25)
                try:
                    return self.status()
                except BridgeError as error:
                    if error.code != "BRIDGE_OFFLINE":
                        raise
        raise BridgeError("BRIDGE_START_FAILED", "Bridge 启动后未在限定时间内就绪")

    def personas(self) -> dict[str, Any]:
        return self._request("GET", "/api/personas")

    def upsert_persona(self, persona_id: str, name: str, system_prompt: str = "", config_json: str = "{}") -> dict[str, Any]:
        return self._request("POST", "/api/personas", {
            "persona_id": persona_id,
            "name": name,
            "system_prompt": system_prompt,
            "config_json": config_json,
        })

    def send(self, content: str, conversation_id: str = "", expected_format: str = "text", timeout_ms: int = 600000, target_id: str = "", persona_id: str = "", task_group_id: str = "") -> dict[str, Any]:
        return self._request("POST", "/api/chat/send", {
            "content": content,
            "conversation_id": conversation_id,
            "expected_format": expected_format,
            "timeout_ms": timeout_ms,
            "target_id": target_id,
            "persona_id": persona_id,
            "task_group_id": task_group_id,
        }, timeout=timeout_ms / 1000 + 20)

    def send_image(self, image_path: str, prompt: str = "请描述这张图片", conversation_id: str = "", expected_format: str = "text", timeout_ms: int = 600000, target_id: str = "") -> dict[str, Any]:
        """Ask the web ChatGPT to understand a local image (clipboard-paste path)."""
        return self._request("POST", "/api/chat/send-image", {
            "image_path": image_path,
            "prompt": prompt,
            "conversation_id": conversation_id,
            "expected_format": expected_format,
            "timeout_ms": timeout_ms,
            "target_id": target_id,
        }, timeout=timeout_ms / 1000 + 20)

    def send_image_only(self, prompt: str = "请描述这些图片", conversation_id: str = "", expected_format: str = "text", timeout_ms: int = 600000, target_id: str = "") -> dict[str, Any]:
        """Send a prompt with images already pasted in the composer (skip paste)."""
        return self._request("POST", "/api/chat/send-image", {
            "image_path": "", "skip_paste": True,
            "prompt": prompt,
            "conversation_id": conversation_id,
            "expected_format": expected_format,
            "timeout_ms": timeout_ms,
            "target_id": target_id,
        }, timeout=timeout_ms / 1000 + 20)


    def read(self, conversation_id: str, after_sequence: int = 0, limit: int = 100) -> dict[str, Any]:
        return self._request("GET", f"/api/chat/messages?conversation_id={urllib.parse.quote(conversation_id)}&after={int(after_sequence)}&limit={int(limit)}")

    def search(self, query: str = "", conversation_id: str = "", role: str = "", limit: int = 100) -> dict[str, Any]:
        params = urllib.parse.urlencode({"q": query, "conversation_id": conversation_id, "role": role, "limit": int(limit)})
        return self._request("GET", f"/api/chat/search?{params}")

    def export(self, conversation_id: str = "", output_format: str = "markdown") -> dict[str, Any]:
        params = urllib.parse.urlencode({"conversation_id": conversation_id, "format": output_format})
        return self._request("GET", f"/api/chat/export?{params}")

    def wait_event(self, conversation_id: str = "current", after_sequence: int = 0, timeout_ms: int = 30000) -> dict[str, Any]:
        return self._request("GET", f"/api/chat/wait?conversation_id={urllib.parse.quote(conversation_id)}&after={int(after_sequence)}&timeout_ms={int(timeout_ms)}", timeout=timeout_ms / 1000 + 5)

    def sync(self, conversation_id: str = "current", target_id: str = "") -> dict[str, Any]:
        return self._request("POST", "/api/chat/sync", {"conversation_id": conversation_id, "target_id": target_id}, timeout=35)

    def cancel(self, request_id: str) -> dict[str, Any]:
        return self._request("POST", f"/api/chat/cancel/{urllib.parse.quote(request_id)}")

    def task_group_submit(self, task_group_id: str, tasks: list[dict[str, Any]], title: str = "") -> dict[str, Any]:
        return self._request(
            "POST", f"/api/task-groups/{urllib.parse.quote(task_group_id)}/submit",
            {"task_group_id": task_group_id, "title": title, "tasks": tasks},
            timeout=max(30, sum(int(item.get("timeout_ms", 600000)) for item in tasks) / 1000 + 30),
        )

    def task_group_status(self, task_group_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/task-groups/{urllib.parse.quote(task_group_id)}")

    def task_status(self, request_id: str) -> dict[str, Any]:
        return self._request("GET", f"/api/tasks/{urllib.parse.quote(request_id)}")
