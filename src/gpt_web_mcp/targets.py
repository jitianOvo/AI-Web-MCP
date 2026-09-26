"""Connected browser target registry used by the V2 multi-target bridge."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TargetConnection:
    connection_id: str
    websocket: Any
    target_id: str = ""
    state: dict[str, Any] = field(default_factory=dict)

    def status(self) -> dict[str, Any]:
        result = dict(self.state)
        result.update({
            "connection_id": self.connection_id,
            "target_id": self.target_id or self.connection_id,
            "connected": True,
        })
        return result


class TargetRegistry:
    """Keep extension sockets separate while retaining a default target."""

    def __init__(self) -> None:
        self.connections: dict[str, TargetConnection] = {}
        self.target_to_connection: dict[str, str] = {}

    def attach(self, connection_id: str, websocket: Any) -> TargetConnection:
        connection = TargetConnection(connection_id, websocket)
        self.connections[connection_id] = connection
        return connection

    def update(self, connection_id: str, payload: dict[str, Any]) -> TargetConnection | None:
        connection = self.connections.get(connection_id)
        if connection is None:
            return None
        target_id = str(payload.get("target_id") or connection.target_id or connection_id)
        old_target_id = connection.target_id
        if old_target_id and old_target_id != target_id:
            self.target_to_connection.pop(old_target_id, None)
        connection.target_id = target_id
        connection.state = {
            "browser": str(payload.get("browser", "chromium")),
            "browser_version": str(payload.get("browser_version", "")),
            "tab_bound": bool(payload.get("tab_bound")),
            "page_ready": bool(payload.get("page_ready")),
            "generating": bool(payload.get("generating")),
            "conversation_title": str(payload.get("conversation_title", "")),
            "tab_id": payload.get("tab_id"),
            "tab_title": str(payload.get("tab_title", "")),
            "tab_url": str(payload.get("tab_url", "")),
            "input_ready": bool(payload.get("input_ready", payload.get("page_ready", False))),
            "is_new_chat": bool(payload.get("is_new_chat")),
            "conversation_id": str(payload.get("conversation_id", "")),
            "last_seen": time.time(),
            "extension_version": str(payload.get("extension_version", "")),
            "tabs": list(payload.get("tabs") or []),
            "updated_at": time.time(),
        }
        self.target_to_connection[target_id] = connection_id
        return connection

    def remove(self, connection_id: str) -> TargetConnection | None:
        connection = self.connections.pop(connection_id, None)
        if connection and connection.target_id and self.target_to_connection.get(connection.target_id) == connection_id:
            self.target_to_connection.pop(connection.target_id, None)
        return connection

    def get(self, target_id: str) -> TargetConnection | None:
        connection_id = self.target_to_connection.get(target_id)
        return self.connections.get(connection_id) if connection_id else None

    def choose(self, target_id: str = "", ready_only: bool = True) -> TargetConnection | None:
        if target_id:
            connection = self.get(target_id)
            if connection and (not ready_only or self.is_ready(connection)):
                return connection
            return None
        for connection in self.connections.values():
            if not ready_only or self.is_ready(connection):
                return connection
        return None

    def choose_control(self) -> TargetConnection | None:
        """Pick a control socket used for agent-driven binding requests."""
        for connection in self.connections.values():
            if connection.target_id in {"unbound", "bound-tab"}:
                return connection
        return next(iter(self.connections.values()), None)

    @staticmethod
    def is_ready(connection: TargetConnection) -> bool:
        return bool(connection.state.get("tab_bound") and connection.state.get("page_ready"))

    def status(self) -> list[dict[str, Any]]:
        return [connection.status() for connection in self.connections.values()]
