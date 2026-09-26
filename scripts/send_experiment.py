#!/usr/bin/env python3
"""Experiment: sync ProseMirror state via Input.insertText, then submit.

Background windows drop CDP key events, so the reliable pipeline is:
  focus + select-all -> Input.insertText (text-input pipe) -> button enabled
  -> submit via synthetic Enter on the synced editor / pointer sequence.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from edge_chat import Cdp, list_tabs  # noqa: E402

SELECT_ALL_FOCUS = r"""
(function(){
  const e = document.querySelector('div.ProseMirror, #prompt-textarea, [contenteditable="true"]');
  if (!e) return 'no_editor';
  e.focus();
  const s = window.getSelection();
  const r = document.createRange();
  r.selectNodeContents(e);
  s.removeAllRanges();
  s.addRange(r);
  return 'focused';
})()
"""

STATE_JS = r"""
(function(){
  const out = {};
  const e = document.querySelector('div.ProseMirror, #prompt-textarea, [contenteditable="true"]');
  out.composer = e ? (e.innerText || '').slice(0, 120) : null;
  const b = Array.from(document.querySelectorAll('main button')).find(x => (x.getAttribute('aria-label')||'') === '发送' || (x.getAttribute('aria-label')||'').includes('Send'));
  out.send = b ? {found:true, disabled:!!b.disabled, ariaDisabled:b.getAttribute('aria-disabled')||''} : {found:false};
  const users = Array.from(document.querySelectorAll('[data-message-author-role="user"]'));
  out.userCount = users.length;
  out.userTexts = users.map(x => (x.innerText||'').trim()).filter(Boolean).slice(-2);
  out.turns = document.querySelectorAll('[data-testid^="conversation-turn-"]').length;
  out.url = location.href;
  return out;
})()
"""


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    prompt = sys.argv[1] if len(sys.argv) > 1 else "请只回复 K9"
    async with aiohttp.ClientSession() as session:
        tabs = await list_tabs(session)
        target = next((t for t in tabs if t.get("url", "").startswith("https://chatgpt.com")), None)
        if not target:
            print(json.dumps({"error": "no chatgpt cdp tab"}))
            return 1
        cdp = Cdp(session, target["webSocketDebuggerUrl"])
        await cdp.connect()
        log = {}

        log["focus"] = await cdp.eval(SELECT_ALL_FOCUS)
        await asyncio.sleep(0.2)
        await cdp.cmd("Input.insertText", {"text": prompt})
        await asyncio.sleep(0.6)
        log["afterInsert"] = await cdp.eval(STATE_JS)

        # window is foreground now: real CDP key events reach the page
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Enter", "code": "Enter", "text": "\r", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        await cdp.cmd("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Enter", "code": "Enter", "windowsVirtualKeyCode": 13, "nativeVirtualKeyCode": 13})
        await asyncio.sleep(1.2)
        log["afterRealEnter"] = await cdp.eval(STATE_JS)

        strategies = {
            "enter_synthetic": r"""
(function(){
  const e = document.querySelector('div.ProseMirror, #prompt-textarea, [contenteditable="true"]');
  if (!e) return 'no_editor';
  e.focus();
  const opts = {key:'Enter', code:'Enter', keyCode:13, which:13, bubbles:true, cancelable:true, composed:true};
  const a = new KeyboardEvent('keydown', opts);
  const b = new KeyboardEvent('keypress', opts);
  const c = new KeyboardEvent('keyup', opts);
  // ProseMirror handles keydown synchronously; dispatch on the editor itself
  e.dispatchEvent(a);
  e.dispatchEvent(b);
  e.dispatchEvent(c);
  return 'dispatched';
})()
""",
            "pointer_sequence": r"""
(function(){
  const b = Array.from(document.querySelectorAll('main button')).find(x => (x.getAttribute('aria-label')||'') === '发送' || (x.getAttribute('aria-label')||'').includes('Send'));
  if (!b) return 'no_button';
  const rect = b.getBoundingClientRect();
  const cx = rect.x + rect.width/2, cy = rect.y + rect.height/2;
  const opts = {bubbles:true, cancelable:true, composed:true, clientX:cx, clientY:cy, button:0};
  b.dispatchEvent(new PointerEvent('pointerdown', {...opts, pointerId:1, isPrimary:true}));
  b.dispatchEvent(new MouseEvent('mousedown', opts));
  b.dispatchEvent(new PointerEvent('pointerup', {...opts, pointerId:1, isPrimary:true}));
  b.dispatchEvent(new MouseEvent('mouseup', opts));
  b.dispatchEvent(new MouseEvent('click', opts));
  return 'dispatched';
})()
""",
            "click_again": r"""
(function(){
  const b = Array.from(document.querySelectorAll('main button')).find(x => (x.getAttribute('aria-label')||'') === '发送' || (x.getAttribute('aria-label')||'').includes('Send'));
  if (!b) return 'no_button';
  if (b.disabled) return 'disabled';
  b.click();
  return 'clicked';
})()
""",
        }

        log["strategies"] = {}
        final = None
        for name, js in strategies.items():
            log["strategies"][name] = await cdp.eval(js)
            await asyncio.sleep(0.8)
            final = await cdp.eval(STATE_JS)
            log["after_" + name] = final
            if final.get("userTexts") or final.get("turns"):
                break

        for i in range(20):
            await asyncio.sleep(0.5)
            final = await cdp.eval(STATE_JS)
            log.setdefault("poll", []).append(final)
            if final.get("userTexts") or final.get("turns"):
                break
        log["final"] = final
        print(json.dumps(log, ensure_ascii=False, indent=2))
        return 0 if final and (final.get("userTexts") or final.get("turns")) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
