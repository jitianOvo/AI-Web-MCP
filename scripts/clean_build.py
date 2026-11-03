"""Preview or remove redundant generated build archives."""

from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="delete redundant archives")
    args = parser.parse_args()
    files = sorted(BUILD.glob("*.zip"), key=lambda path: path.stat().st_mtime, reverse=True)
    latest_by_kind: dict[str, Path] = {}
    redundant: list[Path] = []
    for path in files:
        kind = ("extension" if "extension-" in path.name else "diagnostic" if "diagnostic-" in path.name
                else "unified-skill" if path.name == "AI-Web-MCP-skill.zip"
                else "workflow-skill" if "工作流规范" in path.name else "vision-skill" if "视觉技能" in path.name
                else path.stem)
        if kind not in latest_by_kind:
            latest_by_kind[kind] = path
        else:
            redundant.append(path)
    print(f"build_archives={len(files)} redundant={len(redundant)} apply={args.apply}")
    for path in redundant:
        print(f"{'remove' if args.apply else 'would_remove'} {path.relative_to(ROOT)}")
        if args.apply:
            path.unlink()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
