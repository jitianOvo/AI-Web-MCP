"""Run the project agent helper from any working directory."""
import os
from pathlib import Path
import sys

root = Path(os.environ.get("GPT_WEB_MCP_ROOT", r"D:\桌面\Work\GPT Web MCP"))
sys.path.insert(0, str(root / "src"))
from gpt_web_mcp.agent_cli import main

if __name__ == "__main__":
    raise SystemExit(main())
