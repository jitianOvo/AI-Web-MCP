"""Package the gpt-web-mcp-workflow skill into a reusable zip."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skill" / "gpt-web-mcp-workflow"
BUILD = ROOT / "build"
OUTPUT = BUILD / "AI-Web-MCP-工作流规范.zip"


def main() -> int:
    if not (SKILL_DIR / "SKILL.md").exists():
        print(f"missing SKILL.md: {SKILL_DIR}")
        return 1
    BUILD.mkdir(parents=True, exist_ok=True)
    for skill, output in ((ROOT / "skill" / "ai-web-mcp", BUILD / "AI-Web-MCP-skill.zip"), (SKILL_DIR, OUTPUT),
            (ROOT / "skill" / "gpt-web-vision", BUILD / "AI-Web-MCP-视觉技能.zip")):
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(skill.rglob("*")):
                if path.is_file() and "__pycache__" not in path.parts:
                    archive.write(path, path.relative_to(skill.parent).as_posix())
        print(f"skill_zip={output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
