#!/usr/bin/env python3
"""Minimized-window resilience test.

Minimizes the bound ChatGPT Edge window, sends a short message through the
bridge, and verifies that (a) the extension restores and focuses the window
automatically, and (b) the message round-trips successfully.

Usage:
  python scripts/minimize_test.py
"""

from __future__ import annotations

import ctypes
import json
import sys
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

user32 = ctypes.WinDLL("user32", use_last_error=True)
SW_MINIMIZE = 6


def find_window(title_keyword: str) -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        if length and 0 < length < 300:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if "Edge" in title or "ChatGPT" in title or "chatgpt" in title:
                found.append((hwnd, title))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    if title_keyword:
        found = [(h, t) for h, t in found if title_keyword in t]
    return found


def minimize(title_keyword: str) -> tuple[int, str] | None:
    windows = find_window(title_keyword)
    for hwnd, title in windows:
        if not user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_MINIMIZE)
        return hwnd, title
    return None


def is_minimized(hwnd: int) -> bool:
    return bool(user32.IsIconic(hwnd))


def main() -> int:
    from ai_web_mcp.client import BridgeClient  # noqa: E402

    client = BridgeClient(timeout=120)
    client.ensure_running()
    target = client.bound_tab().get("bound_target_id", "")
    if not target:
        print(json.dumps({"error": "NO_BOUND_TAB"}, ensure_ascii=False))
        return 1

    report = {}
    window = minimize("Edge")
    if not window:
        print(json.dumps({"error": "NO_EDGE_WINDOW"}, ensure_ascii=False))
        return 1
    report["minimized"] = {"hwnd": window[0], "title": window[1]}
    time.sleep(1.0)
    report["confirmed_minimized"] = is_minimized(window[0])

    started = time.time()
    try:
        response = client.send("只回复 MIN-OK", "current", "text", 90000, target)
    except Exception as error:  # noqa: BLE001
        report.update({"success": False, "error": f"{type(error).__name__}: {error}"[:200]})
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 1
    report["send_elapsed"] = round(time.time() - started, 1)
    report["answer"] = str(response.get("result") or "")
    report["success"] = bool(response.get("success")) and "MIN-OK" in str(response.get("result") or "")

    for _ in range(10):
        if not is_minimized(window[0]):
            break
        time.sleep(0.5)
    report["auto_restored"] = not is_minimized(window[0])
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report.get("success") and report.get("auto_restored") else 1


if __name__ == "__main__":
    raise SystemExit(main())
