"""Rotate the local Bridge token and regenerate the unpacked extension config."""

from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gpt_web_mcp.config import CONFIG_PATH, load_config  # noqa: E402
from configure_extension import main as configure_extension  # noqa: E402


def main() -> None:
    config = load_config()
    config["bridge_token"] = secrets.token_urlsafe(32)
    CONFIG_PATH.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    configure_extension()
    print("Bridge token rotated; restart the Bridge and reload the unpacked extension.")


if __name__ == "__main__":
    main()
