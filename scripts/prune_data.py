"""Preview or apply local message retention cleanup."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gpt_web_mcp.config import load_config, resolve_project_path  # noqa: E402
from gpt_web_mcp.storage import Store  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--conversation-id", default="")
    parser.add_argument("--apply", action="store_true", help="actually delete matching messages")
    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be at least 1")
    config = load_config()
    store = Store(resolve_project_path(str(config["database_path"])))
    cutoff = time.time() - args.days * 86400
    count = store.count_messages_before(cutoff, args.conversation_id)
    scope = args.conversation_id or "all conversations"
    if not args.apply:
        print(f"dry_run=true matching_messages={count} older_than_days={args.days} scope={scope}")
        print("add --apply to delete matching messages")
        return 0
    deleted = store.prune_messages_before(cutoff, args.conversation_id)
    print(f"dry_run=false deleted_messages={deleted} older_than_days={args.days} scope={scope}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
