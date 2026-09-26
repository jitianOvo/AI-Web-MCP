"""Package the gpt-web-mcp-workflow skill into a reusable zip."""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skill" / "gpt-web-mcp-workflow"
BUILD = ROOT / "build"
OUTPUT = BUILD / "GPT-Web-MCP-工作流规范.zip"


def main() -> int:
    if not (SKILL_DIR / "SKILL.md").exists():
        print(f"missing SKILL.md: {SKILL_DIR}")
        return 1
    BUILD.mkdir(parents=True, exist_ok=True)
    files = sorted(SKILL_DIR.rglob("*"))
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_dir():
                continue
            rel = path.relative_to(SKILL_DIR.parent)
            archive.write(path, rel.as_posix())
    print(f"skill_zip={OUTPUT}")
    print(f"entries={sum(1 for _ in zipfile.ZipFile(OUTPUT).infolist())}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
