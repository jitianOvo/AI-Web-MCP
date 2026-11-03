"""Preview or remove reproducible project caches while retaining local state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
BROWSER_CACHES = (
    "component_crx_cache", "ProvenanceData", "ProvenanceDataTensors",
    "Edge Entity Extraction", "EdgeLanguageDetectionModel", "GrShaderCache",
    "ShaderCache", "BrowserMetrics", "BrowserMetrics-spare.pma",
    "Speech Recognition", "hyphen-data", "ZxcvbnData",
    "Default/Cache", "Default/Code Cache", "Default/GPUCache",
    "Default/DawnGraphiteCache", "Default/DawnWebGPUCache",
    "Default/Service Worker/CacheStorage",
)


def project_path(path: Path) -> Path:
    resolved = path.resolve()
    if not resolved.is_relative_to(ROOT) or resolved == ROOT or path.is_symlink():
        raise ValueError(f"Refusing cleanup outside the project or through a link: {path}")
    return resolved


def size(path: Path) -> int:
    if path.is_file():
        return path.stat().st_size
    return sum(p.stat().st_size for p in path.rglob("*") if p.is_file() and not p.is_symlink())


def candidates() -> list[Path]:
    paths = [ROOT / "runtime/edge_profile" / name for name in BROWSER_CACHES]
    paths += [ROOT / ".pytest_cache", ROOT / ".mypy_cache"]
    paths += [p for p in ROOT.rglob("__pycache__") if ".git" not in p.parts]
    if (ROOT / "tmp").exists():
        paths += list((ROOT / "tmp").iterdir())
    # Keep the currently versioned extension and both distinct skill packages.
    version = json.loads((ROOT / "extension/manifest.json").read_text(encoding="utf-8"))["version"]
    keep = {f"GPT-Web-MCP-extension-v{version}.zip", f"GPT-Web-MCP-v{version}-windows.zip",
            "GPT-Web-MCP-工作流规范.zip", "GPT-Web-MCP-视觉技能.zip"}
    paths += [p for p in (ROOT / "build").glob("*.zip") if p.name not in keep]
    paths += [ROOT / "build/GPT Web MCP.next.exe"]
    selected: list[Path] = []
    for path in sorted(set(paths), key=lambda p: len(p.parts)):
        if path.exists():
            path = project_path(path)
            if not any(path.is_relative_to(parent) for parent in selected):
                selected.append(path)
    return selected


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="Remove the previewed reproducible files")
    args = parser.parse_args()
    plan = [{"path": str(p.relative_to(ROOT)), "bytes": size(p)} for p in candidates()]
    report = {"apply": args.apply, "planned_bytes": sum(p["bytes"] for p in plan), "items": plan, "errors": []}
    if args.apply:
        for item in plan:
            path = project_path(ROOT / item["path"])
            try:
                if path.is_dir():
                    shutil.rmtree(path)
                else:
                    path.unlink()
            except OSError as error:
                report["errors"].append({"path": item["path"], "error": str(error)})
        output = ROOT / "data/cleanup-last.json"
        output.parent.mkdir(exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return int(bool(report["errors"]))


if __name__ == "__main__":
    raise SystemExit(main())
