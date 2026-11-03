"""Send a synthetic image once, then verify an identical call is replayed."""
import argparse
import json
from pathlib import Path
from ai_web_mcp.client import BridgeClient, BridgeError

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    client = BridgeClient()
    payload = dict(image_path=str(root / "tests/fixtures/vision.png"),
        prompt=f"验收 {args.request_id}：请描述这一张图片的文字、边框颜色和内部形状，说明内部形状是否填充。",
        target_id=args.target, request_id=args.request_id, timeout_ms=120000)
    evidence = {"target_id": args.target, "request_id": args.request_id}
    try:
        evidence["first"] = client.send_image(**payload)
        evidence["replay"] = client.send_image(**payload)
        evidence["task"] = client.task_status(args.request_id)
        page = client.sync_state(target_id=args.target)
        assert evidence["first"]["result"] == evidence["replay"]["result"]
        assert evidence["replay"].get("deduplicated")
        assert evidence["first"]["conversation_id"] == evidence["replay"]["conversation_id"]
        matches = [m for m in page.get("matched_user_messages", []) if args.request_id in m["text"]]
        assert len(matches) == 1, matches
        assert matches[0]["images"] == 1, matches
        evidence["single_image_single_message"] = matches
        evidence["passed"] = True
    except BridgeError as error:
        evidence["error"] = {"code": error.code, "message": error.message, "request_id": error.request_id}
    Path(args.output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence.get("passed") else 1

if __name__ == "__main__":
    raise SystemExit(main())
