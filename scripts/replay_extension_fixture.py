"""Run one local Bridge round trip with a simulated extension target."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from aiohttp import ClientSession


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_web_mcp.client import BridgeClient  # noqa: E402
from ai_web_mcp.config import load_config  # noqa: E402
from ai_web_mcp.protocol import new_request_id  # noqa: E402


async def run_fixture(content: str, result: str, target_id: str, conversation_id: str) -> dict:
    config = load_config()
    client = BridgeClient()
    started = False
    try:
        try:
            client.status()
        except Exception:
            client.ensure_running()
            started = True
        base_url = f"http://{config['host']}:{config['port']}"
        ws_url = f"ws://{config['host']}:{config['port']}/ws/extension?token={config['bridge_token']}"
        headers = {"Origin": "chrome-extension://gpt-web-mcp-fixture"}
        request_headers = {"X-Bridge-Token": config["bridge_token"]}
        async with ClientSession() as session:
            async with session.ws_connect(ws_url, headers=headers) as websocket:
                bridge_ready = await websocket.receive_json()
                await websocket.send_json({
                    "type": "hello",
                    "target_id": target_id,
                    "tab_bound": True,
                    "page_ready": True,
                    "tab_id": 999,
                    "tab_title": "GPT Web MCP Fixture",
                    "tab_url": "https://chatgpt.com/c/" + conversation_id,
                    "conversation_id": conversation_id,
                    "browser": "fixture",
                    "browser_version": "0",
                })
                request_task = asyncio.create_task(session.post(
                    base_url + "/api/chat/send",
                    headers=request_headers,
                    json={
                        "request_id": new_request_id("fixture"),
                        "target_id": target_id,
                        "conversation_id": conversation_id,
                        "content": content,
                        "timeout_ms": 10000,
                    },
                ))
                task = await asyncio.wait_for(websocket.receive_json(), timeout=12)
                if task.get("type") != "task":
                    raise RuntimeError(f"expected task, got {task}")
                await websocket.send_json({
                    "type": "result",
                    "request_id": task["request_id"],
                    "target_id": target_id,
                    "conversation_id": conversation_id,
                    "message_id": "fixture-assistant-1",
                    "result": result,
                })
                response = await request_task
                body = await response.json()
                return {"bridge_ready": bridge_ready["type"], "http_status": response.status, "response": body}
    finally:
        if started:
            try:
                client.shutdown()
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--content", default="fixture request")
    parser.add_argument("--result", default="fixture response")
    parser.add_argument("--target-id", default="fixture-target")
    parser.add_argument("--conversation-id", default="fixture-conversation")
    args = parser.parse_args()
    print(json.dumps(asyncio.run(run_fixture(args.content, args.result, args.target_id, args.conversation_id)), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
