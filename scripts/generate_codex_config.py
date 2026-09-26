"""Generate a project-local Codex MCP configuration snippet."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "config" / "gpt_web_mcp.codex.toml"


def toml_string(value: str) -> str:
    return '"' + value.replace('\\', '/').replace('"', '\\"') + '"'


def main() -> None:
    python_path = ROOT / "runtime" / "venv" / "Scripts" / "python.exe"
    if not python_path.exists():
        python_path = Path("python")
    content = "\n".join([
        "[mcp_servers.gpt_web_mcp]",
        f"command = {toml_string(str(python_path))}",
        f"args = [{toml_string(str(ROOT / 'scripts' / 'run_mcp.py'))}]",
        f"cwd = {toml_string(str(ROOT))}",
        "startup_timeout_sec = 15",
        "tool_timeout_sec = 660",
        "default_tools_approval_mode = \"prompt\"",
        "",
    ])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(content, encoding="utf-8")
    print(OUTPUT)


if __name__ == "__main__":
    main()
