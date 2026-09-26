#!/usr/bin/env python3
"""Print a live composer + message-node dump from the dedicated Edge CDP instance."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import aiohttp

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from edge_chat import Cdp, list_tabs  # noqa: E402

DUMP_JS = r"""
(function(){
  const out = { url: location.href };
  out.editors = Array.from(document.querySelectorAll('[contenteditable="true"]')).map(e => ({
    cls: String(e.className || '').slice(0, 200),
    aria: e.getAttribute('aria-label') || '',
    text: (e.innerText || '').slice(0, 120),
  }));
  out.textareas = Array.from(document.querySelectorAll('main textarea')).map(e => ({
    id: e.id || '', placeholder: e.getAttribute('placeholder') || '',
    value: String(e.value || '').slice(0, 120),
  }));
  out.msgNodes = Array.from(document.querySelectorAll('[data-message-author-role], [data-testid^="conversation-turn-"], main article')).slice(0, 10).map(n => ({
    role: n.getAttribute('data-message-author-role') || '',
    testid: n.getAttribute('data-testid') || '',
    text: (n.innerText || '').slice(0, 80),
    cls: String(n.className || '').slice(0, 80),
  }));
  const active = document.activeElement;
  out.active = active ? { tag: active.tagName, aria: active.getAttribute('aria-label') || '', cls: String(active.className || '').slice(0, 120) } : null;
  return out;
})()
"""


async def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    async with aiohttp.ClientSession() as session:
        tabs = await list_tabs(session)
        target = next((t for t in tabs if t.get("url", "").startswith("https://chatgpt.com")), None)
        if not target:
            print(json.dumps({"error": "no chatgpt cdp tab"}))
            return 1
        cdp = Cdp(session, target["webSocketDebuggerUrl"])
        await cdp.connect()
        print(json.dumps(await cdp.eval(DUMP_JS), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
