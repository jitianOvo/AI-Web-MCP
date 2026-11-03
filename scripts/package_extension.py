"""Package the extension without embedding the local Bridge token."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
EXTENSION = ROOT / "extension"
BUILD = ROOT / "build"


def main() -> None:
    manifest = json.loads((EXTENSION / "manifest.json").read_text(encoding="utf-8"))
    version = str(manifest["version"])
    BUILD.mkdir(parents=True, exist_ok=True)
    output = BUILD / f"AI-Web-MCP-extension-v{version}.zip"
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(EXTENSION.rglob("*")):
            if path.name in {"config.js", "config.example.js"} or path.is_dir():
                continue
            archive.write(path, f"extension/{path.relative_to(EXTENSION).as_posix()}")
        archive.write(EXTENSION / "config.example.js", "extension/config.js")
    print(output)


if __name__ == "__main__":
    main()
