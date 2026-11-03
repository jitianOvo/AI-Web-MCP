"""Stable JSON entry point for agents without an MCP connection."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

from .client import BridgeClient, BridgeError


def select_target(status: dict, requested: str = "") -> str:
    candidates = [t for t in status.get("targets", []) if t.get("tab_bound") and t.get("page_ready")]
    if requested:
        if any(t.get("target_id") == requested for t in candidates):
            return requested
        raise BridgeError("TARGET_NOT_READY", "指定目标未就绪；运行 doctor 查看目标列表")
    targets = sorted({str(t["target_id"]) for t in candidates})
    if len(targets) == 1:
        return targets[0]
    if len(targets) > 1:
        raise BridgeError("TARGET_REQUIRED", "有多个就绪目标，请指定 --target：" + ", ".join(targets))
    raise BridgeError("NO_READY_TARGET", "没有就绪的 ChatGPT 页面；检查扩展并切到正常 ChatGPT 模式")


def doctor(client: BridgeClient) -> dict:
    status = client.status()
    return {"success": True, "bridge": status.get("bridge"), "bridge_version": status.get("bridge_version"),
        "paused": status.get("paused"), "busy": status.get("busy"),
        "targets": [{key: t.get(key) for key in ("target_id", "browser", "extension_version", "tab_bound", "page_ready", "generating", "tab_title")}
            for t in status.get("targets", []) if t.get("tab_bound")],
        "next_action": "使用就绪目标调用 vision；有多个就绪目标时指定 --target。"}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="GPT Web MCP Agent helper; JSON output, no automatic resends")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor", help="只读自检，不发送图片或问题")
    vision = sub.add_parser("vision", help="一次上传、发送和等待回答")
    vision.add_argument("--image", required=True)
    vision.add_argument("--question", default="描述图中对象、文字和布局；无法辨认的内容明确指出。")
    vision.add_argument("--question-file", help="UTF-8 问题文件，优先于 --question")
    vision.add_argument("--target", default="")
    vision.add_argument("--url", default="", help="指定历史会话 URL，复用或打开后在原聊天看图")
    vision.add_argument("--request-id", default="", help="重试同一任务复用此 ID；省略则自动按内容去重")
    vision.add_argument("--timeout-ms", type=int, default=180000)
    vision.add_argument("--output", help="同时保存 JSON 结果")
    task = sub.add_parser("task", help="只读原任务，不重新上传或发送")
    task.add_argument("--request-id", required=True)
    args = parser.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    client = BridgeClient()
    request_id = getattr(args, "request_id", "")
    try:
        if args.command == "doctor":
            result = doctor(client)
        elif args.command == "task":
            result = client.task_status(request_id)
        else:
            image = Path(args.image).expanduser().resolve()
            if not image.is_file():
                raise BridgeError("IMAGE_NOT_FOUND", f"图片不存在：{image}")
            question = Path(args.question_file).read_text(encoding="utf-8") if args.question_file else args.question
            if args.url and args.target:
                raise BridgeError("CONFLICTING_TARGET", "--url 与 --target 不能同时指定")
            if args.url:
                args.target = client.open_conversation(args.url)["target_id"]
            status = client.status()
            if status.get("paused"):
                raise BridgeError("PAUSED", "Bridge 已暂停，请恢复后调用")
            target = select_target(status, args.target)
            if not request_id:
                digest = hashlib.sha256(image.read_bytes()).hexdigest()
                # Match the bridge fingerprint so a lost HTTP reply remains queryable.
                fingerprint = json.dumps([target, "current", digest, question or "请描述这张图片", "text", False],
                    ensure_ascii=False, separators=(",", ":"))
                request_id = "img_" + hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()
            result = client.send_image(str(image), prompt=question, timeout_ms=args.timeout_ms,
                target_id=target, request_id=request_id)
        code = 0
    except BridgeError as error:
        result = {"success": False, "request_id": error.request_id or request_id,
            "error": {"code": error.code, "message": error.message},
            "next_action": "停止发送；运行 doctor，或使用 task --request-id 查询原任务。"}
        code = 1
    except (OSError, ValueError) as error:
        result = {"success": False, "request_id": request_id,
            "error": {"code": "LOCAL_INPUT_ERROR", "message": str(error)}}
        code = 1
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if getattr(args, "output", None):
        destination = Path(args.output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(output, encoding="utf-8")
    print(output)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
