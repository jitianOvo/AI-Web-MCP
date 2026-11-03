"""Shared message helpers for the local bridge and extension."""

from __future__ import annotations

import time
import uuid
from typing import Any

from . import PROTOCOL_VERSION


def new_request_id(prefix: str = "req") -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def make_message(message_type: str, **payload: Any) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "type": message_type,
        "timestamp": time.time(),
        **payload,
    }


def text_hash(role: str, text: str) -> str:
    import hashlib

    return hashlib.sha256(f"{role}\n{text}".encode("utf-8")).hexdigest()
