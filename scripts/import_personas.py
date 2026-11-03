"""Import persona profiles from a project-local JSON array."""

from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from ai_web_mcp.config import load_config, resolve_project_path  # noqa: E402
from ai_web_mcp.storage import Store  # noqa: E402


def main() -> int:
    source = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "config" / "personas.example.json"
    if not source.is_absolute():
        source = ROOT / source
    payload = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise SystemExit("persona file must contain a JSON array")
    config = load_config()
    store = Store(resolve_project_path(str(config["database_path"])))
    imported = 0
    for item in payload:
        if not isinstance(item, dict) or not item.get("persona_id") or not item.get("name"):
            raise SystemExit("each persona requires persona_id and name")
        extra = item.get("config_json", {})
        config_json = extra if isinstance(extra, str) else json.dumps(extra, ensure_ascii=False)
        store.upsert_persona(str(item["persona_id"]), str(item["name"]), str(item.get("system_prompt", "")), config_json)
        imported += 1
    print(f"imported_personas={imported} source={source}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
