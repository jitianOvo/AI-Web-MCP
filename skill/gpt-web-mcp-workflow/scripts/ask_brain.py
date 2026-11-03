#!/usr/bin/env python3
"""问大脑 CLI：把一段提示词发给网页端 ChatGPT 并打印完整回答。

用法:
  python ask_brain.py "提示词" [--timeout-ms 180000] [--target tab-xxx] [--last]

通过本地 GPT Web MCP Bridge 调用；需要 Bridge 在线、扩展已绑定标签页。
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(os.environ.get(
    "AI_WEB_MCP_ROOT", os.environ.get("GPT_WEB_MCP_ROOT",
    r"D:\桌面\Work\AI-Web-MCP"),
)).resolve()
sys.path.insert(0, str(PROJECT_ROOT / "src"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Send a prompt to web ChatGPT via the bridge.")
    parser.add_argument("prompt", nargs="?", default="", help="提示词正文（--last 模式可省略）")
    parser.add_argument("--timeout-ms", type=int, default=180000, help="等待回答超时，默认 180000")
    parser.add_argument("--target", default="", help="target_id，默认自动选择绑定标签页")
    parser.add_argument("--url", default="", help="指定历史 ChatGPT 会话 URL；复用或打开该聊天后继续")
    parser.add_argument("--last", action="store_true", help="只读取指定会话/最近回答，不发新消息")
    parser.add_argument("--conversation", default="current", help="会话 id")
    args = parser.parse_args()

    if not args.last and not args.prompt.strip():
        parser.error("prompt 不能为空（或使用 --last 只读最近回答）")

    from ai_web_mcp.client import BridgeClient, BridgeError  # noqa: E402
    from ai_web_mcp.agent_cli import select_target

    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = BridgeClient(timeout=args.timeout_ms / 1000 + 20)
    try:
        if args.url:
            if args.target or args.conversation != "current":
                parser.error("--url 不与 --target/--conversation 同用，避免指定不同会话")
            opened = client.open_conversation(args.url)
            args.target = opened["target_id"]
            args.conversation = opened["conversation_id"]
        status = client.status()
        if args.last:
            result = client.latest_message(args.conversation, args.target)
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            target = select_target(status, args.target)
            result = client.send(
                args.prompt, args.conversation, "text",
                args.timeout_ms, target,
            )
            print(json.dumps({
                "conversation_id": result.get("conversation_id"),
                "result": result.get("result"),
            }, ensure_ascii=False, indent=2, default=str))
        return 0
    except BridgeError as error:
        print(json.dumps({"code": error.code, "message": error.message, "request_id": error.request_id, "next_action": "查询原任务，不自动重复发送"}, ensure_ascii=False, indent=2))
        return 1
    except Exception as error:  # pragma: no cover
        print(json.dumps({"code": "UNEXPECTED", "message": str(error)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
