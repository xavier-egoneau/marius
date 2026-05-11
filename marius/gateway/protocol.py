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
    "make_dir":   "path",
    "move_path":  "destination",
    "explore_tree": "path",
    "explore_grep": "pattern",
    "explore_summary": "path",
    "run_bash":   "command",
    "web_fetch":  "url",
    "web_search": "query",
    "vision":     "path",
    "skill_view": "name",
    "skill_create": "name",
    "host_agent_list": "agent",
    "host_agent_save": "name",
    "host_agent_delete": "name",
    "host_telegram_configure": "agent",
    "host_status": "agent",
    "host_doctor": "agent",
    "host_logs": "event",
    "host_gateway_restart": "agent",
    "project_list": "limit",
    "project_set_active": "path",
    "approval_list": "limit",
    "approval_decide": "id",
    "approval_forget": "id",
    "secret_ref_list": "name",
    "secret_ref_save": "name",
    "secret_ref_delete": "name",
    "secret_ref_prepare_file": "name",
    "provider_list": "name",
    "provider_save": "name",
    "provider_delete": "id",
    "provider_models": "name",
    "dreaming_run": "archive_sessions",
    "daily_digest": "project_root",
    "self_update_propose": "title",
    "self_update_report_bug": "title",
    "self_update_list": "kind",
    "self_update_show": "id",
    "self_update_apply": "id",
    "self_update_rollback": "id",
    "watch_add": "title",
    "watch_list": "include_disabled",
    "watch_remove": "id",
    "watch_run": "id",
    "open_marius_web": "port",
    "rag_source_add": "name",
    "rag_source_sync": "source_id",
    "rag_search": "query",
    "rag_get": "chunk_id",
    "rag_promote_to_memory": "chunk_id",
    "rag_checklist_add": "list_name",
    "caldav_agenda": "days",
    "caldav_maintenance": "operation",
}


def tool_target(tool_name: str, arguments: dict[str, Any]) -> str:
    key = _TOOL_TARGET_KEYS.get(tool_name, "")
    return str(arguments.get(key, "")) if key else ""


def encode(event: Any) -> bytes:
    return (json.dumps(asdict(event), ensure_ascii=False) + "\n").encode()


def decode(line: str) -> dict[str, Any]:
    return json.loads(line)
