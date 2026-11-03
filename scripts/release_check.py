"""Run the project-local release verification suite."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / "runtime" / "venv" / "Scripts" / "python.exe"
if not PYTHON.exists():
    PYTHON = Path(sys.executable)


def run(label: str, command: list[str], env: dict[str, str] | None = None) -> None:
    print(f"== {label} ==")
    subprocess.run(command, cwd=ROOT, env=env, check=True)


def main() -> int:
    environment = os.environ.copy()
    environment["PYTHONPATH"] = str(ROOT / "src") + os.pathsep + environment.get("PYTHONPATH", "")
    run("version consistency", [str(PYTHON), "scripts/bump_version.py", "--check"], environment)
    run("python tests", [str(PYTHON), "-m", "unittest", "discover", "-s", "tests", "-q"], environment)
    run("compileall", [str(PYTHON), "-m", "compileall", "-q", "src", "scripts"], environment)
    run("installation validation", [str(PYTHON), "scripts/validate_installation.py"], environment)
    run("health report", [str(PYTHON), "scripts/health_report.py"], environment)
    run("documentation links", [str(PYTHON), "scripts/check_docs.py"], environment)
    for script in ("package_extension.py", "package_diagnostic.py"):
        run(script, [str(PYTHON), f"scripts/{script}"], environment)
    run("build cleanup preview", [str(PYTHON), "scripts/clean_build.py"], environment)
    for script in sorted((ROOT / "extension").glob("*.js")):
        run(f"node check {script.name}", ["node", "--check", str(script)], environment)
    run("extension regressions", ["node", "--test", *[str(path) for path in sorted((ROOT / "tests").glob("*.test.cjs"))]], environment)
    run("extension protocol fixture", [str(PYTHON), "scripts/replay_extension_fixture.py"], environment)
    print("release_check=passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
