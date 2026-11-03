"""MCP facade exposed to Codex."""

from __future__ import annotations

from typing import Any

from .client import BridgeClient

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as error:  # pragma: no cover - exercised only before install
    FastMCP = None
    _MCP_IMPORT_ERROR = error
else:
    _MCP_IMPORT_ERROR = None


if FastMCP is not None:
    mcp = FastMCP(
        "gpt-web-mcp",
        instructions=(
            "Use the bound local ChatGPT web tab through the browser bridge. "
            "Each target tab is strictly serial; target_id selects a tab. "
            "Check browser_status before chat_send. Use chat_read with a cursor "
            "for incremental collection. Use task_group_submit for bounded persona batches."
            "List open ChatGPT tabs with list_chatgpt_tabs and pick one with bind_chatgpt_tab. "
            "ask_chatgpt is the high-level send-wait-read flow."
            "For planning-style tasks, use ask_chatgpt to consult the bound web ChatGPT as the planner. "
            "Full workflow rules live in the gpt-web-mcp-workflow skill."
        ),
    )

    @mcp.tool()
    def browser_status() -> dict[str, Any]:
        """Return Bridge, extension, and bound ChatGPT page status."""
        client = BridgeClient()
        client.ensure_running()
        return client.status()

    @mcp.tool()
    def list_chatgpt_tabs() -> dict[str, Any]:
        """List open ChatGPT tabs with tab_id, title, url, active, window, and bound state."""
        client = BridgeClient()
        client.ensure_running()
        return client.tabs()

    @mcp.tool()
    def bind_chatgpt_tab(tab_id: int) -> dict[str, Any]:
        """Bind a specific ChatGPT tab id; returns the target_id used by later tools."""
        client = BridgeClient()
        client.ensure_running()
        return client.bind_tab(tab_id)

    @mcp.tool()
    def get_bound_chatgpt_tab() -> dict[str, Any]:
        """Return the currently bound ChatGPT tab, if any."""
        client = BridgeClient()
        client.ensure_running()
        return client.bound_tab()

    @mcp.tool()
    def get_latest_message(conversation_id: str = "current") -> dict[str, Any]:
        """Read the most recent captured message and response state for a conversation."""
        client = BridgeClient()
        client.ensure_running()
        return client.latest_message(conversation_id)

    @mcp.tool()
    def open_chatgpt_tab(url: str = "") -> dict[str, Any]:
        """Open/bind a ChatGPT URL; reuse an existing matching conversation tab. Omit URL for a new tab."""
        client = BridgeClient()
        client.ensure_running()
        return client.open_tab(url)

    @mcp.tool()
    def open_chatgpt_conversation(url: str) -> dict[str, Any]:
        """Continue an existing ChatGPT /c/<id> URL. Reuse or open exactly that chat and return target_id, conversation_id, url and readiness; does not send a message or create a new chat."""
        client = BridgeClient()
        client.ensure_running()
        return client.open_conversation(url)

    @mcp.tool()
    def new_chat(target_id: str = "") -> dict[str, Any]:
        """Start a fresh ChatGPT chat on the bound tab; returns the new conversation state."""
        client = BridgeClient()
        client.ensure_running()
        return client.new_chat(target_id)

    @mcp.tool()
    def reload_extension(tab_id: int = 0) -> dict[str, Any]:
        """Reload the browser extension and refresh the bound ChatGPT tab automatically."""
        client = BridgeClient()
        client.ensure_running()
        return client.reload_extension(tab_id)

    @mcp.tool()
    def sync_chat_state(conversation_id: str = "current", target_id: str = "") -> dict[str, Any]:
        """Recover the scene: re-sync messages and report page/generation state without resending."""
        client = BridgeClient(timeout=35)
        client.ensure_running()
        return client.sync_state(conversation_id, target_id)

    @mcp.tool()
    def wait_for_response(request_id: str, timeout_ms: int = 120000) -> dict[str, Any]:
        """Wait until a previously submitted request reaches a terminal state."""
        client = BridgeClient(timeout=timeout_ms / 1000 + 10)
        client.ensure_running()
        return client.wait_for_response(request_id, timeout_ms)

    @mcp.tool()
    def get_chat_history(conversation_id: str = "current", limit: int = 100) -> dict[str, Any]:
        """Read local chat history for a conversation, ordered by capture sequence."""
        client = BridgeClient()
        client.ensure_running()
        return client.read(conversation_id, 0, limit)

    @mcp.tool()
    def ask_chatgpt(question: str, conversation_id: str = "current", expected_format: str = "text", timeout_ms: int = 600000, target_id: str = "", new_chat: bool = False) -> dict[str, Any]:
        """High-level V4 flow: ensure a ready tab, optionally start a new chat, send, wait, return the answer."""
        client = BridgeClient(timeout=timeout_ms / 1000 + 20)
        client.ensure_running()
        bound = client.bound_tab()
        effective_target = target_id or bound.get("bound_target_id", "")
        if not effective_target:
            tabs = client.tabs().get("tabs", [])
            if not tabs:
                opened = client.open_tab()
                effective_target = str(opened.get("target_id", ""))
            else:
                raise RuntimeError(f"NO_BOUND_TAB: 存在 {len(tabs)} 个标签页但未绑定，请先调用 bind_chatgpt_tab。")
        if new_chat:
            client.new_chat(effective_target)
        return client.send(question, conversation_id, expected_format, timeout_ms, effective_target)

    @mcp.tool()
    def chat_send(content: str, conversation_id: str = "current", expected_format: str = "text", timeout_ms: int = 600000, target_id: str = "", persona_id: str = "", task_group_id: str = "") -> dict[str, Any]:
        """Send one message to the bound ChatGPT tab and wait for the completed answer."""
        client = BridgeClient(timeout=timeout_ms / 1000 + 20)
        client.ensure_running()
        return client.send(content, conversation_id, expected_format, timeout_ms, target_id, persona_id, task_group_id)

    @mcp.tool()
    def ask_chatgpt_image(image_path: str, question: str = "请描述这张图片", conversation_id: str = "current", timeout_ms: int = 600000, target_id: str = "", request_id: str = "") -> dict[str, Any]:
        """Send a local image to the bound ChatGPT web page for visual understanding.
        Uploads exactly one file and sends question once. Repeated identical requests
        return the original result; use a new request_id for an intentional new analysis.
        On timeout query chat_task_status / chat_read; never resend a text-only question.
        Only needed when the current model lacks vision."""
        client = BridgeClient(timeout=timeout_ms / 1000 + 30)
        client.ensure_running()
        bound = client.bound_tab()
        effective_target = target_id or bound.get("bound_target_id", "")
        if not effective_target:
            raise RuntimeError("NO_BOUND_TAB: 请先绑定 ChatGPT 标签页。")
        return client.send_image(image_path, question, conversation_id, "text", timeout_ms, effective_target, request_id)

    @mcp.tool()
    def persona_upsert(persona_id: str, name: str, system_prompt: str = "", config_json: str = "{}") -> dict[str, Any]:
        """Create or update a reusable persona profile stored by the local Bridge."""
        client = BridgeClient()
        client.ensure_running()
        return client.upsert_persona(persona_id, name, system_prompt, config_json)

    @mcp.tool()
    def persona_list() -> dict[str, Any]:
        """List persona profiles available to task dispatch."""
        client = BridgeClient()
        client.ensure_running()
        return client.personas()

    @mcp.tool()
    def chat_read(conversation_id: str = "current", after_sequence: int = 0, limit: int = 100) -> dict[str, Any]:
        """Read messages after a local SQLite sequence cursor."""
        client = BridgeClient()
        client.ensure_running()
        return client.read(conversation_id, after_sequence, limit)

    @mcp.tool()
    def chat_search(query: str = "", conversation_id: str = "", role: str = "", limit: int = 100) -> dict[str, Any]:
        """Search locally captured messages by text, conversation, and role."""
        client = BridgeClient()
        client.ensure_running()
        return client.search(query, conversation_id, role, limit)

    @mcp.tool()
    def chat_export(conversation_id: str = "", output_format: str = "markdown") -> dict[str, Any]:
        """Export locally captured messages as Markdown or JSON content."""
        client = BridgeClient()
        client.ensure_running()
        return client.export(conversation_id, output_format)

    @mcp.tool()
    def chat_wait_event(conversation_id: str = "current", after_sequence: int = 0, timeout_ms: int = 30000) -> dict[str, Any]:
        """Wait for a newly captured message after a local SQLite sequence cursor."""
        client = BridgeClient(timeout=timeout_ms / 1000 + 5)
        client.ensure_running()
        return client.wait_event(conversation_id, after_sequence, timeout_ms)

    @mcp.tool()
    def chat_sync(conversation_id: str = "current", target_id: str = "") -> dict[str, Any]:
        """Request a snapshot of messages currently rendered in the bound ChatGPT tab."""
        client = BridgeClient(timeout=35)
        client.ensure_running()
        return client.sync(conversation_id, target_id)

    @mcp.tool()
    def chat_cancel(request_id: str) -> dict[str, Any]:
        """Cancel a queued or active ChatGPT request."""
        return BridgeClient().cancel(request_id)

    @mcp.tool()
    def task_group_submit(task_group_id: str, tasks: list[dict[str, Any]], title: str = "") -> dict[str, Any]:
        """Run a bounded batch of persona/target tasks and return per-task results."""
        client = BridgeClient(timeout=max(30, sum(int(item.get("timeout_ms", 600000)) for item in tasks) / 1000 + 30))
        client.ensure_running()
        return client.task_group_submit(task_group_id, tasks, title)

    @mcp.tool()
    def task_group_status(task_group_id: str) -> dict[str, Any]:
        """Read task-group state and its persisted task results."""
        client = BridgeClient()
        client.ensure_running()
        return client.task_group_status(task_group_id)

    @mcp.tool()
    def chat_task_status(request_id: str) -> dict[str, Any]:
        """Read one persisted task, including interrupted Bridge restart state."""
        client = BridgeClient()
        client.ensure_running()
        return client.task_status(request_id)


def main() -> None:
    if FastMCP is None:
        raise RuntimeError("MCP dependency is not installed; run python -m pip install -r requirements.txt") from _MCP_IMPORT_ERROR
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
