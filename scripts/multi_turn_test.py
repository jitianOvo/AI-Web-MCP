#!/usr/bin/env python3
"""Multi-turn context integrity: does the bridge keep one session stable?

Round 1 asks ChatGPT to remember a random token. Later rounds ask for that
token, then build on the previous answer.  Verifies conversation continuity,
no cross-talk with other conversations, and stable completion detection.

Usage:
  python scripts/multi_turn_test.py --rounds 5
"""

from __future__ import annotations

import argparse
import json
import random
import string
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def make_token() -> str:
    return "BRAIN-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))


def main() -> int:
    parser = argparse.ArgumentParser(description="Multi-turn context test")
    parser.add_argument("--rounds", type=int, default=5)
    parser.add_argument("--target", default="")
    parser.add_argument("--timeout-ms", type=int, default=180000)
    args = parser.parse_args()

    from gpt_web_mcp.client import BridgeClient  # noqa: E402

    client = BridgeClient(timeout=args.timeout_ms / 1000 + 30)
    client.ensure_running()
    target = args.target or client.bound_tab().get("bound_target_id", "")
    if not target:
        print(json.dumps({"error": "NO_BOUND_TAB"}, ensure_ascii=False))
        return 1

    token = make_token()
    client.new_chat(target)  # fresh conversation so context checks are clean
    time.sleep(1.5)
    turns = []
    turns.append({
        "round": 1,
        "prompt": f"请记住这个随机令牌，只回复令牌本身：{token}",
        "expect": token,
    })
    for index in range(2, args.rounds + 1):
        if index % 3 == 2:
            prompt = f"我之前让你记住的随机令牌是什么？只回复令牌本身。"
            expect = token
        elif index % 3 == 0:
            prompt = f"承接上一条：把令牌与单词 STAR 组合成一句话，不超过 12 个字。"
            expect = ""
        else:
            prompt = f"继续上一条的句子风格，用一句话总结你我的角色分工，不超过 20 个字。"
            expect = ""
        turns.append({"round": index, "prompt": prompt, "expect": expect})

    results = []
    for turn in turns:
        started = time.time()
        try:
            response = client.send(turn["prompt"], "current", "text", args.timeout_ms, target)
        except Exception as error:  # noqa: BLE001
            record = {"round": turn["round"], "success": False, "error": f"{type(error).__name__}: {error}"[:200]}
            results.append(record)
            print(json.dumps(record, ensure_ascii=False))
            continue
        answer = str(response.get("result") or response.get("text") or "")
        record = {
            "round": turn["round"],
            "success": bool(response.get("success")),
            "elapsed": round(time.time() - started, 1),
            "answer": answer[:160],
            "answer_chars": len(answer),
        }
        if turn["expect"]:
            record["token_found"] = turn["expect"] in answer
        else:
            record["token_found"] = None
        results.append(record)
        print(json.dumps(record, ensure_ascii=False))

    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = ROOT / "tmp" / f"multi_turn_{stamp}.json"
    out.write_text(json.dumps({"token": token, "results": results}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"saved {out}")
    failed = [r for r in results if not r.get("success") or r.get("token_found") is False]
    print(f"rounds={len(results)} failed={len(failed)}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
