"""Provider-aware JSON CLI sharing the MCP BridgeClient and queue."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from .client import BridgeClient, BridgeError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AI Web MCP JSON CLI; no automatic resends")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("doctor")
    sub.add_parser("providers")
    tabs = sub.add_parser("tabs")
    tabs.add_argument("--provider", default="")
    opened = sub.add_parser("open")
    opened.add_argument("--provider", default="chatgpt")
    opened.add_argument("--url", default="")
    opened.add_argument("--new", action="store_true")
    for command in ("ask", "vision", "upload", "send"):
        action = sub.add_parser(command)
        action.add_argument("--target", default="", required=command in {"upload", "send"})
        action.add_argument("--request-id", default="")
        action.add_argument("--timeout-ms", type=int, default=600000)
        action.add_argument("--output", default="")
        if command in {"ask", "vision"}:
            action.add_argument("--provider", default="")
            action.add_argument("--question", default="请描述这张图片" if command == "vision" else "")
            action.add_argument("--question-file", default="")
        if command in {"vision", "upload"}:
            action.add_argument("--image", required=True)
        if command == "send":
            action.add_argument("--content", default="")
            action.add_argument("--content-file", default="")
            action.add_argument("--use-attachments", action="store_true")
    for command in ("task", "cancel"):
        action = sub.add_parser(command)
        action.add_argument("--request-id", required=True)
    history = sub.add_parser("history")
    history.add_argument("--conversation-id", default="current")
    history.add_argument("--limit", type=int, default=100)
    search = sub.add_parser("search")
    search.add_argument("--query", default="")
    search.add_argument("--conversation-id", default="")
    search.add_argument("--role", default="")
    search.add_argument("--limit", type=int, default=100)
    export = sub.add_parser("export")
    export.add_argument("--conversation-id", default="")
    export.add_argument("--format", choices=("markdown", "json"), default="markdown")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    request_id = getattr(args, "request_id", "")
    try:
        client = BridgeClient()
        if args.command not in {"providers", "doctor"}:
            client.ensure_running()
        if args.command == "providers":
            result = client.list_ai_providers()
        elif args.command == "doctor":
            result = {"success": True, "status": client.status(), **client.list_ai_providers()}
        elif args.command == "tabs":
            result = client.list_ai_tabs(args.provider)
        elif args.command == "open":
            result = client.open_ai_chat(args.provider, args.url, args.new)
        elif args.command in {"ask", "vision"}:
            question = Path(args.question_file).read_text(encoding="utf-8-sig") if args.question_file else args.question
            if args.command == "ask":
                result = client.ask_ai(question, args.provider, args.target, request_id, args.timeout_ms)
            else:
                result = client.ask_ai_image(args.image, question, args.provider, args.target, request_id, args.timeout_ms)
        elif args.command == "upload":
            result = client.upload_ai_image(args.image, args.target, request_id, args.timeout_ms)
        elif args.command == "send":
            content = Path(args.content_file).read_text(encoding="utf-8-sig") if args.content_file else args.content
            result = client.send_ai_message(content, args.target, args.use_attachments, request_id, args.timeout_ms)
        elif args.command == "task":
            result = client.task_status(request_id)
        elif args.command == "cancel":
            result = client.cancel(request_id)
        elif args.command == "history":
            result = client.read(args.conversation_id, 0, args.limit)
        elif args.command == "search":
            result = client.search(args.query, args.conversation_id, args.role, args.limit)
        else:
            result = client.export(args.conversation_id, args.format)
        code = 0
    except BridgeError as error:
        result = {"success": False, "request_id": error.request_id or request_id,
                  "error": {"code": error.code, "message": error.message}}
        code = 1
    except (OSError, ValueError) as error:
        result = {"success": False, "request_id": request_id,
                  "error": {"code": "LOCAL_INPUT_ERROR", "message": str(error)}}
        code = 1
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if getattr(args, "output", ""):
        try:
            destination = Path(args.output)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(output, encoding="utf-8")
        except OSError as error:
            output = json.dumps({"success": False, "request_id": result.get("request_id", request_id),
                                 "error": {"code": "OUTPUT_WRITE_FAILED", "message": str(error)}, "response": result}, ensure_ascii=False)
            code = 1
    print(output)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
