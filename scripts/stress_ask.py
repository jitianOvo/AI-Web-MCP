#!/usr/bin/env python3
"""V4 长任务稳定性压测：连续多轮真实网页 ask，统计成功率/重复/完整率。

用法:
  python scripts/stress_ask.py --rounds 10 --target tab-xxx
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="GPT Web MCP V4 长任务压测（纯网页路径）")
    parser.add_argument("--rounds", type=int, default=10)
    parser.add_argument("--target", default="")
    parser.add_argument("--timeout-ms", type=int, default=120000)
    args = parser.parse_args()

    from gpt_web_mcp.client import BridgeClient  # noqa: E402

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = BridgeClient(timeout=args.timeout_ms / 1000 + 20)
    client.ensure_running()
    stats = {
        "rounds": 0, "ok": 0, "failed": 0,
        "timeouts": 0, "dup_rounds": 0, "partial_rounds": 0,
        "total_extra_sec": 0.0, "total_elapsed": 0.0, "errors": [], "recovered": 0,
    }
    for index in range(1, args.rounds + 1):
        prompt = f"请只回复 OK{index}"
        started = time.time()
        try:
            result = client.send(prompt, "current", "text", args.timeout_ms, args.target)
            elapsed = time.time() - started
            stats["total_elapsed"] += elapsed
            if result.get("success"):
                stats["ok"] += 1
                stats["total_extra_sec"] += max(0.0, elapsed - 4)
                answer = str(result.get("result") or result.get("text") or "")
                if answer.strip() != f"OK{index}":
                    stats["partial_rounds"] += 1
                    print(f"round={index} PARTIAL answer={answer[:40]!r}")
                if result.get("recovered"):
                    stats["recovered"] += 1
                print(f"round={index} ok elapsed={elapsed:.1f}s")
            else:
                stats["failed"] += 1
                code = str(result.get("error_code", "ERROR"))
                if code in {"RESPONSE_TIMEOUT", "TIMEOUT"}:
                    stats["timeouts"] += 1
                stats["errors"].append({"round": index, "code": code, "message": str(result.get("error", ""))[:200]})
                print(f"round={index} FAILED code={code}")
        except Exception as error:
            stats["failed"] += 1
            stats["errors"].append({"round": index, "code": "UNEXPECTED", "message": str(error)[:200]})
        stats["rounds"] = index
        time.sleep(0.3)
    stats["send_success_rate"] = round(stats["ok"] / max(1, stats["rounds"]) * 100, 1)
    stats["avg_extra_sec"] = round(stats["total_extra_sec"] / max(1, stats["ok"]), 2)
    stats["avg_elapsed_sec"] = round(stats["total_elapsed"] / max(1, stats["rounds"]), 2)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    return 0 if stats["ok"] == stats["rounds"] and stats["dup_rounds"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
