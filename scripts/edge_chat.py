#!/usr/bin/env python3
"""Dedicated Edge + CDP driver: fully automated ChatGPT Web send/read.

Launch/attach a debug Edge with a persistent profile, send one prompt via the
trusted browser input pipeline, wait for the full answer, and print JSON.

Usage:
  python scripts/edge_chat.py "请只回复 K1" [--timeout 120] [--new]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9333
PROFILE = ROOT / "runtime" / "edge_profile"
CDP_HTTP = f"http://127.0.0.1:{PORT}"

EDITOR_FOCUS_JS = """
(function(){
  const e = document.querySelector('div.ProseMirror, #prompt-textarea, [contenteditable="true"]');
  if (!e) return false;
  e.focus();
  const s = window.getSelection();
  const r = document.createRange();
  r.selectNodeContents(e);
  s.removeAllRanges();
  s.addRange(r);
  return true;
})()
"""

CARET_END_JS = """
(function(){
  const e = document.querySelector('div.ProseMirror, #prompt-textarea, [contenteditable="true"]');
  if (!e) return false;
  const s = window.getSelection();
  const r = document.createRange();
  r.selectNodeContents(e);
  r.collapse(false);
  s.removeAllRanges();
  s.addRange(r);
  return true;
})()
"""

SEND_BUTTON_JS = """
(function(){
  const b = document.querySelector("button[aria-label='发送'], button[data-testid='composer-send-button'], button[data-testid='send-button'], button[aria-label*='Send']");
  if (!b) return null;
  const r = b.getBoundingClientRect();
  return {x: r.x + r.width / 2, y: r.y + r.height / 2, disabled: Boolean(b.disabled)};
})()
"""

READ_STATE_JS = """
(function(){
  const nodes = Array.from(document.querySelectorAll('[data-message-author-role]'));
  const userNodes = nodes.filter(n => n.getAttribute('data-message-author-role') === 'user');
  const asNodes = nodes.filter(n => n.getAttribute('data-message-author-role') === 'assistant');
  const clean = (n) => (n.innerText || n.textContent || '').replace(/\\n{3,}/g, '\\n\\n').trim();
  const last = (arr) => arr.length ? clean(arr[arr.length - 1]) : '';
  const stop = document.querySelector('button[data-testid="stop-button"], button[aria-label*="Stop"]');
  return {
    ready: !!document.querySelector('div.ProseMirror, #prompt-textarea, [contenteditable="true"]'),
    userOnScreen: userNodes.some(n => clean(n)),
    userText: last(userNodes),
    lastAssistant: last(asNodes),
    assistantCount: asNodes.length,
    generating: !!stop,
    url: location.href,
  };
})()
"""


async def launch_edge() -> None:
    if not Path(EDGE).exists():
        raise RuntimeError(f"msedge not found: {EDGE}")
    PROFILE.mkdir(parents=True, exist_ok=True)
    args = [
        EDGE,
        f"--remote-debugging-port={PORT}",
        f"--user-data-dir={PROFILE}",
        "--no-first-run",
        "--no-default-browser-check",
        "--remote-allow-origins=*",
        "about:blank",
    ]
    subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


async def list_tabs(session: aiohttp.ClientSession) -> list[dict]:
    async with session.get(f"{CDP_HTTP}/json/list") as resp:
        return await resp.json()


async def open_tab(session: aiohttp.ClientSession, url: str) -> dict | None:
    quoted = urllib.parse.quote(url, safe="")
    try:
        async with session.put(f"{CDP_HTTP}/json/new?{quoted}") as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception:
        pass
    try:
        async with session.get(f"{CDP_HTTP}/json/new?{quoted}") as resp:
            if resp.status == 200:
                return await resp.json()
    except Exception:
        pass
    return None


class Cdp:
    def __init__(self, session: aiohttp.ClientSession, ws_url: str):
        self.ws = None
        self.session = session
        self.ws_url = ws_url
        self._id = 0
        self._pending: dict[int, asyncio.Future] = {}

    async def connect(self) -> None:
        self.ws = await self.session.ws_connect(self.ws_url, max_msg_size=4 * 1024 * 1024)
        asyncio.create_task(self._reader())

    async def _reader(self) -> None:
        async for message in self.ws:
            if message.type == aiohttp.WSMsgType.TEXT:
                data = json.loads(message.data)
                fut = self._pending.pop(data.get("id"), None)
                if fut and not fut.done():
                    fut.set_result(data)

    async def cmd(self, method: str, params: dict | None = None, timeout: float = 30) -> dict:
        self._id += 1
        future = asyncio.get_running_loop().create_future()
        self._pending[self._id] = future
        await self.ws.send_json({"id": self._id, "method": method, "params": params or {}})
        result = await asyncio.wait_for(future, timeout=timeout)
        if "error" in result and result["error"]:
            raise RuntimeError(f"{method}: {result['error']}")
        return result.get("result", {})

    async def eval(self, expression: str, timeout: float = 15) -> any:
        result = await self.cmd("Runtime.evaluate", {
            "expression": expression, "returnByValue": True, "awaitPromise": True,
        }, timeout=timeout)
        return (result.get("result") or {}).get("value")


def clean_tab_url(url: str) -> bool:
    return bool(url and (url.startswith("https://chatgpt.com/") or url.startswith("https://chat.openai.com/")))


async def send_chatgpt(cdp: Cdp, prompt: str, timeout_s: float = 120, new_tab: bool = False) -> dict:
    # ensure we are on chatgpt
    await cdp.eval("location.href = 'https://chatgpt.com/'")
    await asyncio.sleep(2)
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        state = await cdp.eval(READ_STATE_JS)
        if state and state.get("ready"):
            break
        await asyncio.sleep(0.5)

    await cdp.eval(EDITOR_FOCUS_JS)
    # clear stale content
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "a", "code": "KeyA",
                                             "windowsVirtualKeyCode": 65, "nativeVirtualKeyCode": 65, "modifiers": 2})
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA",
                                             "windowsVirtualKeyCode": 65, "nativeVirtualKeyCode": 65, "modifiers": 2})
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Backspace", "code": "Backspace",
                                             "windowsVirtualKeyCode": 8, "nativeVirtualKeyCode": 8})
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace",
                                             "windowsVirtualKeyCode": 8, "nativeVirtualKeyCode": 8})
    # type text via trusted pipeline (select-all first so insertText replaces)
    # type text character-by-character so ProseMirror registers it as real input
    for char in prompt:
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": char, "text": char, "unmodifiedText": char,
                                                 "windowsVirtualKeyCode": 0, "nativeVirtualKeyCode": 0})
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "char", "key": char, "text": char, "unmodifiedText": char,
                                                 "windowsVirtualKeyCode": 0, "nativeVirtualKeyCode": 0})
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": char, "text": char, "unmodifiedText": char,
                                                 "windowsVirtualKeyCode": 0, "nativeVirtualKeyCode": 0})
    await asyncio.sleep(0.15)
    await cdp.eval(CARET_END_JS)
    # press Enter (Playwright-compatible key sequence)
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "text": "\r",
                                             "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter",
                                             "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})

    # wait user message on screen
    deadline = time.monotonic() + 20
    user_text = ""
    clicked_send = False
    started = time.monotonic()
    while time.monotonic() < deadline:
        state = await cdp.eval(READ_STATE_JS)
        if state and state.get("userText"):
            user_text = state.get("userText", "")
            if prompt in user_text:
                break
        if not clicked_send and time.monotonic() - started > 2.5:
            clicked_send = True
            btn = await cdp.eval(SEND_BUTTON_JS)
            if btn:
                await cdp.cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": btn["x"], "y": btn["y"], "button": "left", "clickCount": 1})
                await cdp.cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": btn["x"], "y": btn["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(0.4)

    # wait assistant completion
    deadline = time.monotonic() + timeout_s
    last_text = ""
    stable_since = 0.0
    answer = ""
    while time.monotonic() < deadline:
        state = await cdp.eval(READ_STATE_JS)
        text = state.get("lastAssistant", "") if state else ""
        if text != last_text:
            last_text = text
            stable_since = time.monotonic()
        generating = bool(state and state.get("generating"))
        if text and not generating and last_text and time.monotonic() - stable_since >= 0.9:
            answer = text
            break
        await asyncio.sleep(0.3)

    return {
        "user_message_on_screen": bool(user_text),
        "user_text": user_text,
        "answer": answer,
        "assistant_count": 0,
        "completed": bool(answer),
    }


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("prompt", nargs="?", default="")
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--new", action="store_true")
    parser.add_argument("--state", action="store_true", help="只读当前页面状态，不发消息")
    args = parser.parse_args()
    if not args.state and not args.prompt.strip():
        parser.error("prompt 不能为空（或使用 --state 只读状态）")

    try:
        async with aiohttp.ClientSession() as session:
            try:
                tabs = await list_tabs(session)
            except Exception:
                tabs = []
            if not tabs:
                await launch_edge()
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    try:
                        tabs = await list_tabs(session)
                        if tabs:
                            break
                    except Exception:
                        pass
                    await asyncio.sleep(0.5)
            target = None
            if not args.new and tabs:
                target = next((t for t in tabs if clean_tab_url(t.get("url", ""))), None)
            if not target:
                target = await open_tab(session, "https://chatgpt.com/")
            if not target:
                print(json.dumps({"error": "no cdp tab", "code": "CDP_TAB_NOT_FOUND"}))
                return 1
            cdp = Cdp(session, target["webSocketDebuggerUrl"])
            await cdp.connect()
            if args.state:
                state = await cdp.eval(READ_STATE_JS)
                info = await cdp.eval("(function(){return {title: document.title, body: document.body ? document.body.innerText.slice(0, 400) : ''};})()")
                print(json.dumps({"state": state, "page": info}, ensure_ascii=False, indent=2))
                return 0
            result = await send_chatgpt(cdp, args.prompt, timeout_s=args.timeout, new_tab=args.new)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("completed") else 1
    except Exception as error:  # noqa: BLE001
        print(json.dumps({"error": str(error), "code": "EDGE_CDP_FAILED"}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(asyncio.run(main()))
