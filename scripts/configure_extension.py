"""Write the local Bridge token into the unpacked extension config."""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "config" / "config.json"
OUTPUT = ROOT / "extension" / "config.js"


def main() -> None:
    if not CONFIG.exists():
        raise SystemExit("config/config.json does not exist; start the Bridge once first")
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    host = str(config.get("host", "127.0.0.1"))
    port = int(config.get("port", 8765))
    token = str(config.get("bridge_token", ""))
    if not token:
        raise SystemExit("bridge_token is empty")
    content = (
        "globalThis.GPT_WEB_MCP_CONFIG = Object.freeze({\n"
        f"  websocketUrl: \"ws://{host}:{port}/ws/extension\",\n"
        f"  bridgeToken: {json.dumps(token)},\n"
        "  reconnectDelayMs: 2000,\n"
        "  targetId: \"bound-tab\"\n"
        "});\n"
    )
    OUTPUT.write_text(content, encoding="utf-8")
    print(f"wrote {OUTPUT}")


if __name__ == "__main__":
    main()
