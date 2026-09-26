#!/usr/bin/env python3
"""Submit-method comparison after composer state is synced.

The composer now gets text via Input.insertText (state synced, button enabled).
This script tries DOM click, CDP mouse click, then CDP Enter, and reports which
one actually puts a user message on screen.  Helps isolate whether Enter events
are being dropped because the window is not foreground.
"""

from __future__ import annotations

import asyncio
import ctypes
import json
import sys
import time
from ctypes import wintypes
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from edge_chat import Cdp, list_tabs  # noqa: E402

STATE_JS = r"""
(function(){
  const e = document.querySelector('div.ProseMirror[contenteditable="true"]');
  const b = Array.from(document.querySelectorAll('main button')).find(x => (x.getAttribute('aria-label')||'') === '发送' || (x.getAttribute('aria-label')||'').includes('Send'));
  const users = Array.from(document.querySelectorAll('main [class*="bg-user-message"]'));
  return {
    composer: e ? (e.innerText || '').slice(0, 80) : null,
    button: b ? {found:true, disabled:!!b.disabled, aria:b.getAttribute('aria-disabled')||''} : {found:false},
    userCount: users.length,
    userTexts: users.map(n => (n.innerText||'').trim()).slice(-2),
    url: location.href,
  };
})()
"""

BUTTON_RECT_JS = r"""
(function(){
  const b = Array.from(document.querySelectorAll('main button')).find(x => (x.getAttribute('aria-label')||'') === '发送' || (x.getAttribute('aria-label')||'').includes('Send'));
  if (!b) return null;
  const r = b.getBoundingClientRect();
  return {x: r.x + r.width/2, y: r.y + r.height/2, disabled: !!b.disabled};
})()
"""

CLICK_JS = r"""
(function(){
  const b = Array.from(document.querySelectorAll('main button')).find(x => (x.getAttribute('aria-label')||'') === '发送' || (x.getAttribute('aria-label')||'').includes('Send'));
  if (!b) return 'no_button';
  if (b.disabled) return 'disabled';
  b.click();
  return 'clicked';
})()
"""

user32 = ctypes.WinDLL("user32", use_last_error=True)


def focus_window(title_keyword: str) -> None:
    """Bring the first visible window whose title contains keyword to foreground."""
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    targets: list[int] = []

    def callback(hwnd, _lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length and 0 < length < 300:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if title_keyword in buf.value:
                targets.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    for hwnd in targets:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, 9)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.3)


async def wait_user_message(cdp: Cdp, timeout_s: float = 20) -> dict:
    deadline = time.monotonic() + timeout_s
    state = {}
    while time.monotonic() < deadline:
        state = await cdp.eval(STATE_JS)
        if state.get("userTexts"):
            break
        await asyncio.sleep(0.5)
    return state


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    prompt = sys.argv[1] if len(sys.argv) > 1 else "请只回复 S1"
    async with aiohttp.ClientSession() as session:
        tabs = await list_tabs(session)
        page = next((t for t in tabs if t.get("type") == "page" and "chatgpt" in t.get("url", "")), None)
        if not page:
            print(json.dumps({"error": "no chatgpt page"}))
            return 1
        cdp = Cdp(session, page["webSocketDebuggerUrl"])
        await cdp.connect()
        log = {}

        # Sync text through the trusted pipe.
        await cdp.eval("(function(){const e=document.querySelector('div.ProseMirror[contenteditable=\"true\"][aria-label=\"询问 ChatGPT\"], div.ProseMirror[contenteditable=\"true\"][aria-label=\"Ask ChatGPT\"]'); if(!e) return 'no_composer'; e.focus(); const s=window.getSelection(); const r=document.createRange(); r.selectNodeContents(e); s.removeAllRanges(); s.addRange(r); return 'focused';})()")
        await asyncio.sleep(0.2)
        await cdp.cmd("Input.insertText", {"text": prompt})
        await asyncio.sleep(0.6)
        log["afterInsert"] = await cdp.eval(STATE_JS)
        log["button"] = await cdp.eval(BUTTON_RECT_JS)

        methods = {}

        # 1) DOM click (extension trap: does React accept it?)
        result = await cdp.eval(CLICK_JS)
        methods["dom_click"] = result
        state = await wait_user_message(cdp, 10)
        methods["dom_click_user"] = state.get("userTexts")
        log["after_dom_click"] = await cdp.eval(STATE_JS)
        if state.get("userTexts"):
            log["winner"] = "dom_click"
            print(json.dumps(log, ensure_ascii=False, indent=2))
            return 0

        # 2) CDP mouse click on the enabled button (requires foreground window)
        focus_window("Microsoft Edge")
        await asyncio.sleep(0.8)
        btn = await cdp.eval(BUTTON_RECT_JS)
        log["button2"] = btn
        if btn and not btn.get("disabled"):
            await cdp.cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": btn["x"], "y": btn["y"], "button": "none"})
            await cdp.cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": btn["x"], "y": btn["y"], "button": "left", "clickCount": 1})
            await cdp.cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": btn["x"], "y": btn["y"], "button": "left", "clickCount": 1})
            methods["cdp_click"] = "sent"
        else:
            methods["cdp_click"] = "skipped"
        state = await wait_user_message(cdp, 12)
        methods["cdp_click_user"] = state.get("userTexts")
        log["after_cdp_click"] = await cdp.eval(STATE_JS)
        if state.get("userTexts"):
            log["winner"] = "cdp_click"
            print(json.dumps(log, ensure_ascii=False, indent=2))
            return 0

        # 3) CDP Enter on the focused composer
        await cdp.eval("(function(){const e=document.querySelector('div.ProseMirror[contenteditable=\"true\"][aria-label=\"询问 ChatGPT\"], div.ProseMirror[contenteditable=\"true\"][aria-label=\"Ask ChatGPT\"]'); if(e) e.focus();})()")
        await asyncio.sleep(0.3)
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "char", "key": "Enter", "text": "\r", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        methods["cdp_enter"] = "sent"
        state = await wait_user_message(cdp, 12)
        methods["cdp_enter_user"] = state.get("userTexts")
        log["after_cdp_enter"] = await cdp.eval(STATE_JS)
        if state.get("userTexts"):
            log["winner"] = "cdp_enter"

        log["methods"] = methods
        print(json.dumps(log, ensure_ascii=False, indent=2))
        return 0 if log.get("winner") else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
