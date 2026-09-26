#!/usr/bin/env python3
"""Bring the dedicated Edge (or any ChatGPT Edge window) to the foreground."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

SW_RESTORE = 9


def find_chatgpt_windows() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        if length and 0 < length < 300:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            if "ChatGPT" in title or "Edge" in title:
                found.append((hwnd, title))
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found


def main() -> int:
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else ""  # optional exact-ish title filter
    windows = find_chatgpt_windows() if not keyword else [w for w in find_chatgpt_windows() if keyword in w[1]]
    if not windows:
        print(json_dump({"error": "no window", "keyword": keyword, "matches": []}))
        return 1
    for hwnd, title in windows:
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        user32.SetForegroundWindow(hwnd)
        print(json_dump({"focused": hwnd, "title": title}))
    return 0



def json_dump(value) -> str:
    import json
    return json.dumps(value, ensure_ascii=False)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
