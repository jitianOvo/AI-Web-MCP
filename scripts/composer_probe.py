#!/usr/bin/env python3
"""Composer state probe: diff DOM/editor state before and after an input.

Attaches to the dedicated Edge CDP instance (port 9333), snapshots the
ChatGPT composer DOM plus send-button state, optionally performs a
programmatic input, and writes a trace for later diffing against a
physical (human) input trace.

Usage:
  python scripts/composer_probe.py --mode snapshot   # read current state
  python scripts/composer_probe.py --mode program    # programmatic input + snapshot
  python scripts/composer_probe.py --mode send       # type, enter, click send, watch user message
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from edge_chat import Cdp, list_tabs  # noqa: E402

PORT = 9333
CDP_HTTP = f"http://127.0.0.1:{PORT}"

SNAPSHOT_JS = r"""
(function(){
  const out = { at: Date.now(), url: location.href, path: location.pathname };
  const input = document.querySelector('div.ProseMirror, #prompt-textarea, [contenteditable="true"]');
  out.input = input ? {
    tag: input.tagName, id: input.id || '', cls: String(input.className || '').slice(0, 240),
    aria: input.getAttribute('aria-label') || '', role: input.getAttribute('role') || '',
    contenteditable: input.getAttribute('contenteditable'),
    dataLexical: input.getAttribute('data-lexical-editor'),
    innerText: (input.innerText || '').slice(0, 200),
    textContent: (input.textContent || '').slice(0, 200),
    childTags: Array.from(input.querySelectorAll('*')).map(e => e.tagName).slice(0, 40),
  } : null;
  const active = document.activeElement;
  out.activeElement = active ? {
    tag: active.tagName, id: active.id || '', cls: String(active.className || '').slice(0, 160),
    aria: active.getAttribute('aria-label') || '', ce: active.getAttribute('contenteditable'),
  } : null;
  const inputs = Array.from(document.querySelectorAll('main [contenteditable="true"], main textarea')).map((el, i) => ({
    i, tag: el.tagName, id: el.id || '', cls: String(el.className || '').slice(0, 160),
    aria: el.getAttribute('aria-label') || '', placeholder: el.getAttribute('data-placeholder') || '',
  }));
  out.mainInputs = inputs;
  out.forms = Array.from(document.querySelectorAll('form')).map((f, i) => ({
    i, cls: String(f.className || '').slice(0, 160), datatype: f.getAttribute('data-type') || '',
    buttons: Array.from(f.querySelectorAll('button')).map(b => ({
      aria: b.getAttribute('aria-label') || '', testid: b.getAttribute('data-testid') || '',
      disabled: !!b.disabled, ariaDisabled: b.getAttribute('aria-disabled') || '',
      cls: String(b.className || '').slice(0, 100), visible: !!b.offsetParent,
      text: (b.textContent || '').trim().slice(0, 30),
    })).slice(0, 12),
  }));
  out.lowerButtons = Array.from(document.querySelectorAll('main button')).filter(b => {
    const r = b.getBoundingClientRect();
    return r.height > 0 && r.bottom > window.innerHeight * 0.55 && r.right > window.innerWidth * 0.5;
  }).map(b => ({
    aria: b.getAttribute('aria-label') || '', testid: b.getAttribute('data-testid') || '',
    disabled: !!b.disabled, ariaDisabled: b.getAttribute('aria-disabled') || '',
    cls: String(b.className || '').slice(0, 100),
  })).slice(0, 15);
  return out;
})()
"""

EVENTS_JS = r"""
(function(){
  window.__gptTrace = [];
  const types = ['pointerdown','mousedown','focus','focusin','keydown','keypress','beforeinput','input','keyup','compositionstart','compositionupdate','compositionend','selectionchange','change','pointerup','click'];
  const mark = (type) => (e) => {
    if (window.__gptTrace.length >= 400) return;
    const input = document.querySelector('div.ProseMirror, #prompt-textarea, [contenteditable="true"]');
    window.__gptTrace.push({
      type, t: performance.now(),
      target: (e.target && (e.target.tagName + (e.target.id ? '#'+e.target.id : ''))) || '',
      cls: (e.target && String(e.target.className || '').slice(0, 80)) || '',
      data: e.data != null ? String(e.data).slice(0, 40) : null,
      inputType: e.inputType || null,
      key: e.key || null, code: e.code || null,
      isTrusted: e.isTrusted, defaultPrevented: e.defaultPrevented,
      composer: input ? (input.innerText || '').slice(0, 80) : '',
      active: document.activeElement ? document.activeElement.tagName : '',
    });
  };
  types.forEach(t => document.addEventListener(t, mark(t), true));
  return true;
})()
"""

READ_TRACE_JS = r"""
(function(){
  const trace = window.__gptTrace || [];
  delete window.__gptTrace;
  return trace;
})()
"""

SEND_BUTTON_JS = r"""
(function(){
  const b = Array.from(document.querySelectorAll('main button')).find(x => (x.getAttribute('aria-label')||'') === '发送' || (x.getAttribute('aria-label')||'').includes('Send'));
  if (!b) return {found:false};
  const r = b.getBoundingClientRect();
  return {found:true, disabled:!!b.disabled, ariaDisabled:b.getAttribute('aria-disabled')||'', x:r.x+r.width/2, y:r.y+r.height/2, aria:b.getAttribute('aria-label')||''};
})()
"""

USER_MESSAGES_JS = r"""
(function(){
  const n = Array.from(document.querySelectorAll('[data-message-author-role="user"]'));
  return {
    count: n.length,
    texts: n.map(x => (x.innerText || '').trim()).filter(Boolean).slice(-2),
    url: location.href,
  };
})()
"""

FOCUS_JS = r"""
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


async def _wait_ready(cdp: Cdp) -> None:
    current = await cdp.eval("location.href")
    if not str(current or "").startswith("https://chatgpt.com"):
        await cdp.eval("location.href = 'https://chatgpt.com/'"); await asyncio.sleep(1.5)
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if await cdp.eval("!!document.querySelector('div.ProseMirror, #prompt-textarea, [contenteditable=\"true\"]')"):
            return
        await asyncio.sleep(0.4)


async def _type_chars(cdp: Cdp, prompt: str) -> None:
    for char in prompt:
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": char, "text": char, "unmodifiedText": char})
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "char", "key": char, "text": char, "unmodifiedText": char})
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": char, "text": char, "unmodifiedText": char})


async def _press_enter(cdp: Cdp) -> None:
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "text": "\r", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})


async def _clear_composer(cdp: Cdp) -> None:
    await cdp.eval(FOCUS_JS)
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "nativeVirtualKeyCode": 65, "modifiers": 2})
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "windowsVirtualKeyCode": 65, "nativeVirtualKeyCode": 65, "modifiers": 2})
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "rawKeyDown", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8, "nativeVirtualKeyCode": 8})
    await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Backspace", "code": "Backspace", "windowsVirtualKeyCode": 8, "nativeVirtualKeyCode": 8})


async def snapshot(cdp: Cdp, mode: str, prompt: str = "") -> dict:
    await _wait_ready(cdp)
    before = await cdp.eval(SNAPSHOT_JS)

    result: dict = {"mode": mode, "prompt": prompt, "before": before}
    if mode == "program":
        await cdp.eval(EVENTS_JS)
        await _clear_composer(cdp)
        await _type_chars(cdp, prompt)
        await asyncio.sleep(0.3)
        result["afterInsert"] = await cdp.eval(SNAPSHOT_JS)
        result["eventsInsert"] = await cdp.eval(READ_TRACE_JS)
        await _press_enter(cdp)
        await asyncio.sleep(0.5)
        result["afterEnter"] = await cdp.eval(SNAPSHOT_JS)
        result["eventsEnter"] = await cdp.eval(READ_TRACE_JS)
        result["userOnScreen"] = await cdp.eval("(function(){const n=Array.from(document.querySelectorAll('[data-message-author-role=\"user\"]')); return n.some(x=>(x.innerText||'').trim().length>0);})()")
    return result


async def send_probe(cdp: Cdp, prompt: str, timeout_s: float = 60) -> dict:
    """Type via CDP char pipeline, press Enter, then click send if enabled."""
    await _wait_ready(cdp)
    await _clear_composer(cdp)
    await cdp.eval(EVENTS_JS)
    await _type_chars(cdp, prompt)
    await asyncio.sleep(0.35)
    result = {"prompt": prompt, "buttonAfterType": await cdp.eval(SEND_BUTTON_JS)}
    await _press_enter(cdp)
    await asyncio.sleep(0.5)
    result["buttonAfterEnter"] = await cdp.eval(SEND_BUTTON_JS)
    result["userAfterEnter"] = await cdp.eval(USER_MESSAGES_JS)
    btn = result["buttonAfterEnter"]
    if btn and btn.get("found") and not btn.get("disabled"):
        await cdp.cmd("Input.dispatchMouseEvent", {"type": "mousePressed", "x": btn["x"], "y": btn["y"], "button": "left", "clickCount": 1})
        await cdp.cmd("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": btn["x"], "y": btn["y"], "button": "left", "clickCount": 1})
        result["clicked"] = True
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        state = await cdp.eval(USER_MESSAGES_JS)
        result["lastUserState"] = state
        if state.get("texts"):
            break
        await asyncio.sleep(0.5)
    result["userOnScreen"] = bool((result.get("lastUserState") or {}).get("texts"))
    result["events"] = await cdp.eval(READ_TRACE_JS)
    return result


async def main() -> int:
    parser = argparse.ArgumentParser(description="Composer state probe")
    parser.add_argument("--mode", choices=["snapshot", "program", "send"], default="snapshot")
    parser.add_argument("--prompt", default="请只回复 K1")
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--out", default=str(ROOT / "tmp" / "composer_trace.json"))
    args = parser.parse_args()

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    async with aiohttp.ClientSession() as session:
        tabs = await list_tabs(session)
        target = next((t for t in tabs if t.get("url", "").startswith("https://chatgpt.com")), None)
        if not target:
            print(json.dumps({"error": "no chatgpt cdp tab"}))
            return 1
        cdp = Cdp(session, target["webSocketDebuggerUrl"])
        await cdp.connect()
        if args.mode == "send":
            result = await send_probe(cdp, args.prompt, args.timeout)
        else:
            result = await snapshot(cdp, args.mode, args.prompt)
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({
            "saved": str(out),
            "mode": args.mode,
            "url": result.get("before", {}).get("url") or (result.get("lastUserState") or {}).get("url"),
            "inputFound": "before" in result and bool(result.get("before", {}).get("input")),
            "buttonAfterEnter": result.get("buttonAfterEnter"),
            "clicked": result.get("clicked", False),
            "userOnScreen": result.get("userOnScreen"),
            "userTexts": (result.get("lastUserState") or {}).get("texts"),
        }, ensure_ascii=False, indent=2))
        return 0 if (args.mode != "send" or result.get("userOnScreen")) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
