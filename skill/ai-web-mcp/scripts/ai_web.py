"""Installed-skill launcher for the unified project CLI."""
import os
from pathlib import Path
import runpy

root = Path(os.environ.get('AI_WEB_MCP_ROOT', os.environ.get('GPT_WEB_MCP_ROOT', r'D:\桌面\Work\AI-Web-MCP'))).resolve()
script = root / 'scripts' / 'ai_web.py'
if not script.is_file():
    raise SystemExit('Set AI_WEB_MCP_ROOT to the AI-Web-MCP installation directory')
runpy.run_path(str(script), run_name='__main__')
