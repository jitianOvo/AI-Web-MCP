"""Local HTTP client used by the MCP facade."""

from __future__ import annotations

import json
import hashlib
import os
import re
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
from .providers import (canonical_provider, detect_provider, normalize_ai_url,
                        conversation_id_from_url, conversation_urls_match, list_provider_capabilities)
from .protocol import new_request_id


_START_LOCK = threading.Lock()


def normalize_chatgpt_url(url: str, require_conversation: bool = False) -> str:
    """Validate an explicit browser destination without accepting arbitrary origins."""
    if not isinstance(url, str) or any(ord(char) <= 32 for char in url) or "\\" in url:
        raise ValueError("必须提供完整 HTTPS ChatGPT 会话 URL")
    parsed = urllib.parse.urlsplit(url or "https://chatgpt.com/")
    if (parsed.scheme != "https" or parsed.netloc not in {"chatgpt.com", "chat.openai.com"}
            or parsed.query or parsed.fragment):
        raise ValueError("仅接受 chatgpt.com 或 chat.openai.com 的 HTTPS 会话 URL，不带查询或片段")
    path = parsed.path.rstrip("/")
    if not re.fullmatch(r"(?:/g/[A-Za-z0-9_-]+)?/c/[A-Za-z0-9_-]+", path):
        if path or require_conversation:
            raise ValueError("历史会话 URL 必须包含 /c/<conversation_id>")
    return f"https://{parsed.netloc}{path or '/'}"


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
            if method == "POST" and path in {"/api/chat/send-image", "/api/chat/send"}:
                raise BridgeError("DELIVERY_UNCERTAIN", "请求响应未收到，请查询原 request_id，禁止自动重复发送", str((payload or {}).get("request_id", ""))) from error
            raise BridgeError("BRIDGE_OFFLINE", f"本地 Bridge 未响应：{error}") from error
        if not result.get("success", False):
            detail = result.get("error") or {}
            raise BridgeError(str(detail.get("code", "BRIDGE_ERROR")), str(detail.get("message", "Bridge 请求失败")), str(result.get("request_id", "")))
        return result

    def status(self) -> dict[str, Any]:
        return self._request("GET", "/api/status", timeout=3).get("status", {})

    def tabs(self) -> dict[str, Any]:
        return self._request("GET", "/api/tabs")

    def list_ai_providers(self) -> dict[str, Any]:
        return {"success": True, "providers": list_provider_capabilities()}

    def list_ai_tabs(self, provider: str = "") -> dict[str, Any]:
        try:
            provider = canonical_provider(provider, allow_empty=True)
        except ValueError as error:
            raise BridgeError("INVALID_PROVIDER", str(error)) from error
        return self._request("GET", "/api/tabs?" + urllib.parse.urlencode({"provider": provider}))

    def select_ai_target(self, provider: str = "", target_id: str = "") -> dict[str, Any]:
        try:
            provider = canonical_provider(provider, allow_empty=True)
        except ValueError as error:
            raise BridgeError("INVALID_PROVIDER", str(error)) from error
        candidates = [target for target in self.status().get("targets", [])
                      if target.get("connected", True) and target.get("tab_bound") and target.get("page_ready")]
        if target_id:
            candidates = [target for target in candidates if target.get("target_id") == target_id]
            if not candidates:
                raise BridgeError("TARGET_NOT_READY", "指定目标未就绪")
        elif provider:
            candidates = [target for target in candidates if self._target_provider(target) == provider]
        if len(candidates) != 1:
            raise BridgeError("TARGET_REQUIRED" if candidates else "NO_READY_TARGET",
                              "有多个就绪目标，请指定 target_id" if candidates else "没有匹配的就绪目标")
        if provider and self._target_provider(candidates[0]) != provider:
            raise BridgeError("PROVIDER_MISMATCH", "指定目标与提供方不一致")
        return {**candidates[0], "provider": self._target_provider(candidates[0])}

    @staticmethod
    def _target_provider(target: dict[str, Any]) -> str:
        return str(target.get("provider") or detect_provider(str(target.get("tab_url", ""))) or "chatgpt")

    def open_ai_chat(self, provider: str = "chatgpt", url: str = "", new_chat: bool = False) -> dict[str, Any]:
        try:
            provider = canonical_provider(provider)
            destination = normalize_ai_url(provider, url)
        except ValueError as error:
            raise BridgeError("INVALID_AI_URL", str(error)) from error
        result = self._request("POST", "/api/tabs/open", {"provider": provider, "url": destination}, timeout=60)
        expected_id = conversation_id_from_url(provider, destination)
        if expected_id and (not conversation_urls_match(provider, str(result.get("url", "")), destination)
                            or result.get("conversation_id") != expected_id):
            raise BridgeError("CONVERSATION_URL_MISMATCH", "扩展未确认指定会话", str(result.get("request_id", "")))
        if new_chat:
            state = self._request("POST", "/api/chat/new", {"provider": provider, "target_id": result.get("target_id", "")}, timeout=35)
            result.update(state)
            result["url"] = str(state.get("url") or normalize_ai_url(provider))
            result["conversation_id"] = str(state.get("conversation_id") or "")
            result["reused"] = False
            result["new_chat"] = True
        return result

    def _send_ai(self, content: str, *, provider: str = "", target_id: str = "", request_id: str = "",
                 timeout_ms: int = 600000, image_path: str = "", operation: str = "text") -> dict[str, Any]:
        target = self.select_ai_target(provider, target_id)
        actual_provider = target["provider"]
        conversation_id = str(target.get("conversation_id") or "")
        try:
            if target.get("tab_url"):
                conversation_id = conversation_id_from_url(actual_provider, target["tab_url"]) or conversation_id
        except ValueError:
            pass
        conversation_id = conversation_id or "current"
        payload = {"provider": actual_provider, "target_id": target["target_id"], "conversation_id": conversation_id,
                   "request_id": request_id, "timeout_ms": timeout_ms, "expected_format": "text"}
        if operation == "text":
            payload.update(content=content, request_id=request_id or new_request_id("ai"))
            endpoint = "/api/chat/send"
        else:
            digest = "existing-attachment:" + str(target.get("attachment_revision", ""))
            if operation != "send_attachments":
                image = Path(image_path).expanduser().resolve()
                if not image.is_file():
                    raise BridgeError("IMAGE_NOT_FOUND", f"图片不存在：{image}", request_id)
                digest = hashlib.sha256(image.read_bytes()).hexdigest()
                image_path = str(image)
            fingerprint = hashlib.sha256(json.dumps(
                [actual_provider, target["target_id"], conversation_id if conversation_id != "current" else "current:" + str(target.get("conversation_generation", 0)), operation, digest, content, "text"],
                ensure_ascii=False, separators=(",", ":"),
            ).encode("utf-8")).hexdigest()
            automatic_id = new_request_id("img") if operation in {"send_attachments", "upload_image"} else "img_" + fingerprint
            payload.update(prompt=content, image_path=image_path, request_id=request_id or automatic_id,
                           skip_paste=operation == "send_attachments", upload_only=operation == "upload_image")
            endpoint = "/api/chat/send-image"
        return self._request("POST", endpoint, payload, timeout=timeout_ms / 1000 + 20)

    def ask_ai(self, question: str, provider: str = "", target_id: str = "", request_id: str = "", timeout_ms: int = 600000) -> dict[str, Any]:
        return self._send_ai(question, provider=provider, target_id=target_id, request_id=request_id, timeout_ms=timeout_ms)

    def ask_ai_image(self, image_path: str, question: str = "请描述这张图片", provider: str = "", target_id: str = "", request_id: str = "", timeout_ms: int = 600000) -> dict[str, Any]:
        return self._send_ai(question, provider=provider, target_id=target_id, request_id=request_id,
                             timeout_ms=timeout_ms, image_path=image_path, operation="vision")

    def upload_ai_image(self, image_path: str, target_id: str, request_id: str = "", timeout_ms: int = 600000) -> dict[str, Any]:
        return self._send_ai("", target_id=target_id, request_id=request_id, timeout_ms=timeout_ms,
                             image_path=image_path, operation="upload_image")

    def send_ai_message(self, content: str, target_id: str, use_attachments: bool = False, request_id: str = "", timeout_ms: int = 600000) -> dict[str, Any]:
        return self._send_ai(content, target_id=target_id, request_id=request_id, timeout_ms=timeout_ms,
                             operation="send_attachments" if use_attachments else "text")

    def bind_tab(self, tab_id: int) -> dict[str, Any]:
        return self._request("POST", "/api/tabs/bind", {"tab_id": int(tab_id)}, timeout=15)

    def bound_tab(self) -> dict[str, Any]:
        tabs = self.tabs().get("tabs", [])
        bound = next((item for item in tabs if item.get("bound_target_id")), None)
        return bound or {"tab_id": None, "bound_target_id": "", "title": "", "url": ""}

    def latest_message(self, conversation_id: str = "current") -> dict[str, Any]:
        return self._request("GET", f"/api/chat/latest?conversation_id={urllib.parse.quote(conversation_id)}")

    def open_tab(self, url: str = "") -> dict[str, Any]:
        try:
            destination = normalize_chatgpt_url(url)
        except ValueError as error:
            raise BridgeError("INVALID_CHATGPT_URL", str(error)) from error
        return self._request("POST", "/api/tabs/open", {"url": destination}, timeout=60)

    def open_conversation(self, url: str) -> dict[str, Any]:
        try:
            destination = normalize_chatgpt_url(url, require_conversation=True)
        except ValueError as error:
            raise BridgeError("INVALID_CHATGPT_URL", str(error)) from error
        result = self.open_tab(destination)
        if not result.get("ready"):
            raise BridgeError("TARGET_NOT_READY", "历史会话页面尚未就绪", str(result.get("request_id", "")))
        try:
            actual_url = normalize_chatgpt_url(result.get("url", ""), require_conversation=True)
        except ValueError:
            actual_url = ""
        if actual_url != destination or result.get("conversation_id") != destination.rsplit("/", 1)[-1]:
            raise BridgeError("CONVERSATION_URL_MISMATCH", "扩展未确认指定会话地址；请刷新扩展后查询目标状态", str(result.get("request_id", "")))
        return result

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
                [sys.executable, "-m", "ai_web_mcp.bridge"],
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

    def send(self, content: str, conversation_id: str = "", expected_format: str = "text", timeout_ms: int = 600000, target_id: str = "", persona_id: str = "", task_group_id: str = "", input_backend: str = "") -> dict[str, Any]:
        return self._request("POST", "/api/chat/send", {
            "content": content,
            "conversation_id": conversation_id,
            "expected_format": expected_format,
            "timeout_ms": timeout_ms,
            "target_id": target_id,
            "persona_id": persona_id,
            "task_group_id": task_group_id,
            "input_backend": input_backend,
        }, timeout=timeout_ms / 1000 + 20)

    def send_image(self, image_path: str, prompt: str = "请描述这张图片", conversation_id: str = "", expected_format: str = "text", timeout_ms: int = 600000, target_id: str = "", request_id: str = "") -> dict[str, Any]:
        """Upload one local image. Reuse request_id to recover without resending."""
        return self._request("POST", "/api/chat/send-image", {
            "image_path": image_path,
            "request_id": request_id,
            "prompt": prompt,
            "conversation_id": conversation_id,
            "expected_format": expected_format,
            "timeout_ms": timeout_ms,
            "target_id": target_id,
        }, timeout=timeout_ms / 1000 + 20)

    def send_image_only(self, prompt: str = "请描述这些图片", conversation_id: str = "", expected_format: str = "text", timeout_ms: int = 600000, target_id: str = "", request_id: str = "") -> dict[str, Any]:
        """Send a prompt with images already pasted in the composer (skip paste)."""
        return self._request("POST", "/api/chat/send-image", {
            "image_path": "", "skip_paste": True,
            "request_id": request_id,
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
