"""Protocole gateway Marius — JSON-lines sur socket Unix.

Client → serveur : Input, Command, Ping, PermissionResponse
Serveur → client : Welcome, Delta, ToolStart, ToolResult,
                   PermissionRequest, Done, Error, Pong, Status
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

# ── client → serveur ──────────────────────────────────────────────────────────


@dataclass
class InputEvent:
    text: str
    type: str = "input"


@dataclass
class CommandEvent:
    cmd: str
    type: str = "command"


@dataclass
class PingEvent:
    type: str = "ping"


@dataclass
class PermissionResponseEvent:
    request_id: str
    approved: bool
    type: str = "permission_response"


# ── serveur → client ──────────────────────────────────────────────────────────


@dataclass
class WelcomeEvent:
    agent: str
    model: str
    provider: str
    loaded_context: list[str] = field(default_factory=list)
    type: str = "welcome"


@dataclass
class DeltaEvent:
    text: str
    type: str = "delta"


@dataclass
class ToolStartEvent:
    name: str
    target: str = ""
    type: str = "tool_start"


@dataclass
class ToolResultEvent:
    name: str
    ok: bool
    type: str = "tool_result"


@dataclass
class PermissionRequestEvent:
    tool_name: str
    reason: str
    request_id: str
    type: str = "permission_request"


@dataclass
class DoneEvent:
    type: str = "done"


@dataclass
class ErrorEvent:
    message: str
    type: str = "error"


@dataclass
class PongEvent:
    type: str = "pong"


@dataclass
class StatusEvent:
    message: str
    type: str = "status"


# ── sérialisation ─────────────────────────────────────────────────────────────

_TOOL_TARGET_KEYS: dict[str, str] = {
    "read_file":  "path",
    "list_dir":   "path",
    "write_file": "path",
    "run_bash":   "command",
    "web_fetch":  "url",
    "web_search": "query",
    "skill_view": "name",
}


def tool_target(tool_name: str, arguments: dict[str, Any]) -> str:
    key = _TOOL_TARGET_KEYS.get(tool_name, "")
    return str(arguments.get(key, "")) if key else ""


def encode(event: Any) -> bytes:
    return (json.dumps(asdict(event), ensure_ascii=False) + "\n").encode()


def decode(line: str) -> dict[str, Any]:
    return json.loads(line)
