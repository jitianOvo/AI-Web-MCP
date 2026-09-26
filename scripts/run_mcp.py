"""Source-checkout entry point for Codex MCP configuration."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from gpt_web_mcp.mcp_server import main  # noqa: E402


if __name__ == "__main__":
    main()
