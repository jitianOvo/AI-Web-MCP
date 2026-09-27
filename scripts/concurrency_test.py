"""Two-target concurrency probe for GPT Web MCP.

Sends one distinct message to each bound ChatGPT tab at the same time and
checks that answers are isolated (each reply contains only its own token).
"""

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gpt_web_mcp.client import BridgeClient  # noqa: E402

TOKEN_A = "4173"
TOKEN_B = "9268"


def probe(target_id: str, token: str, results: list, index: int) -> None:
    client = BridgeClient()
    prompt = f"并发测试：请只回复令牌 {token}，不要回复任何其他内容。"
    try:
        started = time.monotonic()
        reply = client.send(prompt, timeout_ms=120000, target_id=target_id, input_backend='dom')
        elapsed = round(time.monotonic() - started, 1)
        text = str(reply.get("content") or reply.get("result") or "")
        ok_own = token in text
        other = TOKEN_B if token == TOKEN_A else TOKEN_A
        ok_clean = other not in text
        results[index] = {
            "target_id": target_id,
            "token": token,
            "elapsed_s": elapsed,
            "success": reply.get("success", True),
            "own_token_found": ok_own,
            "other_token_absent": ok_clean,
            "conversation_id": reply.get("conversation_id", ""),
            "reply_head": text[:120],
        }
    except Exception as error:  # noqa: BLE001
        results[index] = {"target_id": target_id, "error": str(error)}


def main() -> int:
    client = BridgeClient()
    status = client.status()
    ready = [t for t in status.get("targets", []) if t.get("page_ready") and t.get("input_ready") and str(t.get("target_id", "")).startswith("tab-")]
    if len(ready) < 2:
        print("need two ready targets, found", [t.get("target_id") for t in ready])
        return 1
    target_a = str(ready[0]["target_id"])
    target_b = str(ready[1]["target_id"])

    results: list = [None, None]
    threads = [
        threading.Thread(target=probe, args=(target_a, TOKEN_A, results, 0)),
        threading.Thread(target=probe, args=(target_b, TOKEN_B, results, 1)),
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    passed = True
    for item in results:
        print(item)
        if item.get("error") or not item.get("own_token_found") or not item.get("other_token_absent"):
            passed = False
    print("CONCURRENCY_PASS" if passed else "CONCURRENCY_FAIL")
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
