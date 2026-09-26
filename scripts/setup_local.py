"""Prepare all project-local generated configuration files."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from configure_extension import main as configure_extension  # noqa: E402
from generate_codex_config import main as generate_codex_config  # noqa: E402
from validate_installation import main as validate_installation  # noqa: E402


def main() -> int:
    configure_extension()
    generate_codex_config()
    return validate_installation()


if __name__ == "__main__":
    raise SystemExit(main())
