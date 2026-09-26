"""Read-only local installation checks."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from gpt_web_mcp import __version__  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    checks: list[tuple[str, bool]] = []
    checks.append(("config/config.json", (ROOT / "config" / "config.json").exists()))
    checks.append(("extension/config.js", (ROOT / "extension" / "config.js").exists()))
    checks.append(("extension/manifest.json", (ROOT / "extension" / "manifest.json").exists()))
    try:
        manifest = json.loads((ROOT / "extension" / "manifest.json").read_text(encoding="utf-8"))
        checks.append(("manifest_version=3", manifest.get("manifest_version") == 3))
        checks.append(("bridge/extension version", manifest.get("version") == __version__))
    except Exception:
        checks.append(("manifest JSON", False))
    checks.append(("runtime/venv", (ROOT / "runtime" / "venv").exists()))
    for name, passed in checks:
        print(f"{'OK' if passed else 'FAIL'} {name}")
    return 0 if all(passed for _, passed in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
