"""Print a token-free local GPT Web MCP health report."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gpt_web_mcp.client import BridgeClient, BridgeError  # noqa: E402
from gpt_web_mcp.config import load_config, resolve_project_path  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    config = load_config()
    bridge = BridgeClient()
    try:
        status = {"online": True, "status": bridge.status()}
    except BridgeError as error:
        status = {"online": False, "error_code": error.code, "message": error.message}
    report = {
        "project_root": str(ROOT),
        "bridge": status,
        "extension_config_exists": (ROOT / "extension" / "config.js").exists(),
        "manifest_exists": (ROOT / "extension" / "manifest.json").exists(),
        "database_path": str(resolve_project_path(str(config["database_path"]))),
        "logs_path": str(ROOT / "logs"),
        "build_archives": sorted(path.name for path in (ROOT / "build").glob("*.zip")) if (ROOT / "build").exists() else [],
        "browser_live_acceptance": "pending_browser",
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
