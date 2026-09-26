"""Create a token-free diagnostic archive from project metadata and docs."""

from __future__ import annotations

import json
import zipfile
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def main() -> None:
    manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
    version = str(manifest["version"])
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    BUILD.mkdir(parents=True, exist_ok=True)
    output = BUILD / f"GPT-Web-MCP-diagnostic-v{version}-{stamp}.zip"
    include_files = [
        ROOT / "README.md",
        ROOT / "requirements.txt",
        ROOT / "pyproject.toml",
        ROOT / "config" / "config.example.json",
        ROOT / "config" / "personas.example.json",
        ROOT / "config" / "gpt_web_mcp.codex.toml",
        ROOT / "extension" / "manifest.json",
        ROOT / "extension" / "config.example.js",
    ]
    include_files.extend(sorted((ROOT / "docs").glob("*.md")))
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in include_files:
            if path.exists():
                archive.write(path, path.relative_to(ROOT).as_posix())
    print(output)


if __name__ == "__main__":
    main()
