"""Host administration tools for Marius.

Standalone wrappers around host diagnostics and guarded actions. These tools
expose host state/actions to the LLM, but never replace its final answer.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from marius.channels.telegram.config import TelegramChannelConfig
from marius.config.contracts import (
    ADMIN_ONLY_TOOLS,
    ALL_TOOLS,
    AgentConfig,
    MariusConfig,
    default_tools_for_role,
    effective_tools_for_role,
)
from marius.config.doctor import Section, format_report_text, run_doctor
from marius.config.store import ConfigStore
from marius.gateway.launcher import is_running as gateway_is_running
from marius.gateway.launcher import restart as gateway_restart
from marius.gateway.service import (
    agent_active_state,
    agent_enabled_state,
    is_service_installed,
    is_systemd_available,
)
from marius.kernel.contracts import ToolResult
from marius.kernel.scheduler import validate_hhmm
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.provider_config.store import ProviderStore
from marius.storage.log_store import LogEntry, preview, read_logs

StatusRunner = Callable[[str], bool]
DoctorRunner = Callable[[str | None], list[Section]]
RestartRunner = Callable[[str, float, str], tuple[bool, str, dict[str, Any]]]
_AGENT_NAME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9_-]{0,63}$")


def make_host_admin_tools(
    *,
    config_path: Path | None = None,
    provider_path: Path | None = None,
    telegram_path: Path | None = None,
    secret_ref_path: Path | None = None,
    log_path: Path | None = None,
    status_runner: StatusRunner | None = None,
    doctor_runner: DoctorRunner | None = None,
    restart_runner: RestartRunner | None = None,
) -> dict[str, ToolEntry]:
    """Build host/admin tools with injectable dependencies for tests."""

    store = ConfigStore(path=config_path) if config_path is not None else ConfigStore()
    provider_store = ProviderStore(path=provider_path) if provider_path is not None else ProviderStore()
    tg_path = Path(telegram_path) if telegram_path is not None else None
    is_running = status_runner or gateway_is_running
    run_diagnostics = doctor_runner or run_doctor
    restart_gateway = restart_runner or (lambda agent, delay, mode: gateway_restart(agent, delay_seconds=delay, mode=mode))

    def host_agent_list(arguments: dict[str, Any]) -> ToolResult:
        cfg = store.load()
        if cfg is None:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Marius config not found or unreadable.",
                error="config_unavailable",
            )
        include_tools = bool(arguments.get("include_tools", False))
        rows = []
        lines = [f"Marius agents: {len(cfg.agents)} configured, main={cfg.main_agent}."]
        for name in sorted(cfg.agents):
            agent = cfg.agents[name]
            suffix = " (main)" if name == cfg.main_agent else ""
            lines.append(f"- {name}{suffix}: {agent.provider_id} / {agent.model}, {len(agent.skills)} skill(s)")
            row = _agent_config_data(agent)
            if not include_tools:
                row.pop("tools", None)
            rows.append(row)
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="\n".join(lines),
            data={"main_agent": cfg.main_agent, "agents": rows},
        )

    def host_agent_save(arguments: dict[str, Any]) -> ToolResult:
        cfg = _ensure_config(store)
        if cfg is None:
            return ToolResult(tool_call_id="", ok=False, summary="Marius config not found or unreadable.", error="config_unavailable")

        name = _optional_text(arguments.get("name"))
        if not name or not _valid_agent_name(name):
            return ToolResult(tool_call_id="", ok=False, summary="Invalid agent name.", error="invalid_agent_name")

        providers = provider_store.load()
        provider_ids = {provider.id for provider in providers}
        existing = cfg.agents.get(name)
        provider_id = _optional_text(arguments.get("provider_id")) or (existing.provider_id if existing else None)
        if not provider_id:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `provider_id` is required when creating an agent.", error="missing_arg:provider_id")
        if provider_ids and provider_id not in provider_ids:
            return ToolResult(tool_call_id="", ok=False, summary=f"Unknown provider_id: {provider_id}", error="unknown_provider")

        provider_model = next((provider.model for provider in providers if provider.id == provider_id), "")
        model = _optional_text(arguments.get("model")) or (existing.model if existing else provider_model)
        if not model:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `model` is required when creating an agent.", error="missing_arg:model")
        try:
            role = existing.role if existing else "agent"
            tools = _resolve_toolset(
                existing.tools if existing else default_tools_for_role(role),
                arguments,
                role=role,
            )
        except ValueError as exc:
            return ToolResult(tool_call_id="", ok=False, summary=str(exc), error="invalid_tools")

        skills = _resolve_string_list(existing.skills if existing else [], arguments, replace_key="skills", add_key="add_skills", remove_key="remove_skills")
        scheduler_enabled = _optional_bool(arguments.get("scheduler_enabled"), existing.scheduler_enabled if existing else True)

        # role : préserver si existant, sinon "agent" (l'admin ne se crée pas via ce tool)
        role = existing.role if existing else "agent"
        agent = AgentConfig(
            name=name,
            provider_id=provider_id,
            model=model,
            role=role,
            tools=tools,
            skills=skills,
            scheduler_enabled=scheduler_enabled,
        )
        cfg.agents[name] = agent
        if bool(arguments.get("set_main", False)):
            cfg.main_agent = name
        store.save(cfg)
        verb = "updated" if existing else "created"
        main_note = " and set as main agent" if cfg.main_agent == name and bool(arguments.get("set_main", False)) else ""
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Agent {verb}: {name}{main_note}.",
            data={"agent": _agent_config_data(agent), "main_agent": cfg.main_agent, "created": existing is None},
        )

    def host_agent_delete(arguments: dict[str, Any]) -> ToolResult:
        cfg = _ensure_config(store)
        if cfg is None:
            return ToolResult(tool_call_id="", ok=False, summary="Marius config not found or unreadable.", error="config_unavailable")
        name = _optional_text(arguments.get("name"))
        if not name:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `name` missing.", error="missing_arg:name")
        if name not in cfg.agents:
            return ToolResult(tool_call_id="", ok=False, summary=f"Agent not found: {name}", error="agent_not_found")
        if not bool(arguments.get("confirm", False)):
            return ToolResult(tool_call_id="", ok=False, summary="Deletion requires `confirm: true`.", error="confirmation_required")
        if name == cfg.main_agent:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Cannot delete the main agent.",
                error="main_agent_delete_forbidden",
            )
        if cfg.agents[name].is_admin:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Cannot delete the admin agent.",
                error="admin_delete_forbidden",
            )

        del cfg.agents[name]
        store.save(cfg)
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Agent deleted: {name}. Main agent is {cfg.main_agent}.",
            data={"deleted": name, "main_agent": cfg.main_agent, "agents": sorted(cfg.agents)},
        )

    def host_telegram_configure(arguments: dict[str, Any]) -> ToolResult:
        if any(key in arguments for key in ("token", "raw_token", "bot_token")):
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Raw Telegram tokens are refused. Use `token_ref` with `env:NAME`, `file:/path/to/token` or `secret:NAME`.",
                error="raw_secret_refused",
            )

        current = _load_telegram_config(tg_path)
        token_ref = _optional_text(arguments.get("token_ref"))
        token = _read_secret_ref(token_ref, secret_ref_path=secret_ref_path) if token_ref else (current.token if current else "")
        if not token:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Telegram token missing. Provide `token_ref` as `env:NAME`, `file:/path/to/token` or `secret:NAME`.",
                error="missing_token_ref",
            )

        agent_name = _optional_text(arguments.get("agent")) or (current.agent_name if current else "main")
        allowed_users = _int_list(arguments.get("allowed_users"), current.allowed_users if current else [])
        allowed_chats = _int_list(arguments.get("allowed_chats"), current.allowed_chats if current else [])
        enabled = _optional_bool(arguments.get("enabled"), current.enabled if current else True)
        cfg = TelegramChannelConfig(
            token=token,
            agent_name=agent_name,
            allowed_users=allowed_users,
            allowed_chats=allowed_chats,
            enabled=enabled,
        )
        _save_telegram_config(cfg, tg_path)
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Telegram configured for agent {agent_name}; enabled={enabled}; token stored from reference.",
            data={
                "agent": agent_name,
                "enabled": enabled,
                "allowed_users": allowed_users,
                "allowed_chats": allowed_chats,
                "token_source": _secret_source_label(token_ref) if token_ref else "existing",
                "token_stored": bool(token),
            },
        )

    def host_status(arguments: dict[str, Any]) -> ToolResult:
        cfg = store.load()
        if cfg is None:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Marius config not found or unreadable.",
                error="config_unavailable",
            )

        requested_agent = _optional_text(arguments.get("agent"))
        names = [requested_agent] if requested_agent else sorted(cfg.agents) or [cfg.main_agent]
        agents = [_agent_status(cfg, name, is_running) for name in names]
        missing = [row["name"] for row in agents if not row["configured"]]
        lines = [
            f"Marius host status: {len(cfg.agents)} configured agent(s), main={cfg.main_agent}, permissions={cfg.permission_mode}.",
        ]
        for row in agents:
            if not row["configured"]:
                lines.append(f"- {row['name']}: not configured")
                continue
            gateway = "running" if row["gateway_running"] else "stopped"
            lines.append(
                f"- {row['name']}: {row['provider_id']} / {row['model']}, "
                f"{gateway}, {row['tool_count']} tool(s), {row['skill_count']} skill(s)"
            )

        return ToolResult(
            tool_call_id="",
            ok=not missing,
            summary="\n".join(lines),
            data={
                "main_agent": cfg.main_agent,
                "permission_mode": cfg.permission_mode,
                "systemd": _systemd_status(),
                "agents": agents,
            },
            error="agent_not_found" if missing else None,
        )

    def host_doctor(arguments: dict[str, Any]) -> ToolResult:
        agent = _optional_text(arguments.get("agent"))
        sections = run_diagnostics(agent)
        text, errors = format_report_text(sections)
        return ToolResult(
            tool_call_id="",
            ok=errors == 0,
            summary=text,
            data={"agent": agent, "errors": errors, "sections": [_section_data(section) for section in sections]},
            error="doctor_failed" if errors else None,
        )

    def host_logs(arguments: dict[str, Any]) -> ToolResult:
        limit = _bounded_int(arguments.get("limit"), default=30, minimum=1, maximum=200)
        event_filter = _optional_text(arguments.get("event"))
        agent_filter = _optional_text(arguments.get("agent"))
        read_limit = min(1000, limit * 5) if (event_filter or agent_filter) else limit
        entries = read_logs(limit=read_limit, log_path=log_path)
        filtered = [
            entry for entry in entries
            if _matches_log(entry, event=event_filter, agent=agent_filter)
        ][-limit:]

        lines = [f"Marius logs: {len(filtered)} entrie(s)."]
        for entry in filtered:
            data_preview = preview(json.dumps(entry.data, ensure_ascii=False, sort_keys=True), limit=180)
            lines.append(f"- {entry.timestamp} {entry.event}: {data_preview}")

        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="\n".join(lines),
            data={
                "limit": limit,
                "event": event_filter,
                "agent": agent_filter,
                "entries": [asdict(entry) for entry in filtered],
            },
        )

    def host_gateway_restart(arguments: dict[str, Any]) -> ToolResult:
        cfg = _ensure_config(store)
        if cfg is None:
            return ToolResult(tool_call_id="", ok=False, summary="Marius config not found or unreadable.", error="config_unavailable")
        agent = _optional_text(arguments.get("agent")) or cfg.main_agent
        if agent not in cfg.agents:
            return ToolResult(tool_call_id="", ok=False, summary=f"Agent not found: {agent}", error="agent_not_found")
        if not bool(arguments.get("confirm", False)):
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Gateway restart requires `confirm: true` because it interrupts active connections.",
                error="confirmation_required",
            )
        delay = _bounded_float(arguments.get("delay_seconds"), default=1.5, minimum=0.5, maximum=30.0)
        mode = _optional_text(arguments.get("mode")) or "auto"
        if mode not in ("auto", "direct", "systemd"):
            return ToolResult(tool_call_id="", ok=False, summary="Invalid restart mode. Use auto, direct or systemd.", error="invalid_mode")
        ok, error, data = restart_gateway(agent, delay, mode)
        if not ok:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary=f"Gateway restart could not be scheduled for {agent}: {error or 'unknown error'}",
                error="restart_schedule_failed",
                data={"agent": agent, "mode": mode, "delay_seconds": delay, "error": error},
            )
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Gateway restart scheduled for agent {agent} in {delay:.1f}s ({mode}).",
            data={"agent": agent, "mode": mode, "delay_seconds": delay, **dict(data)},
        )

    return {
        "host_agent_list": ToolEntry(
            definition=ToolDefinition(
                name="host_agent_list",
                description="List Marius agents from config without exposing provider secrets.",
                parameters={
                    "type": "object",
                    "properties": {
                        "include_tools": {"type": "boolean", "description": "Include each agent's tool list."},
                    },
                    "required": [],
                },
            ),
            handler=host_agent_list,
        ),
        "host_agent_save": ToolEntry(
            definition=ToolDefinition(
                name="host_agent_save",
                description="Create or update a Marius agent config atomically.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "provider_id": {"type": "string"},
                        "model": {"type": "string"},
                        "tools": {"type": "array", "items": {"type": "string"}},
                        "add_tools": {"type": "array", "items": {"type": "string"}},
                        "remove_tools": {"type": "array", "items": {"type": "string"}},
                        "skills": {"type": "array", "items": {"type": "string"}},
                        "add_skills": {"type": "array", "items": {"type": "string"}},
                        "remove_skills": {"type": "array", "items": {"type": "string"}},
                        "scheduler_enabled": {"type": "boolean"},
                        "set_main": {"type": "boolean"},
                    },
                    "required": ["name"],
                },
            ),
            handler=host_agent_save,
        ),
        "host_agent_delete": ToolEntry(
            definition=ToolDefinition(
                name="host_agent_delete",
                description="Delete a configured Marius agent after explicit confirmation.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "confirm": {"type": "boolean", "description": "Must be true to delete."},
                    },
                    "required": ["name", "confirm"],
                },
            ),
            handler=host_agent_delete,
        ),
        "host_telegram_configure": ToolEntry(
            definition=ToolDefinition(
                name="host_telegram_configure",
                description="Configure Telegram using a secret reference, never a raw token.",
                parameters={
                    "type": "object",
                    "properties": {
                        "token_ref": {"type": "string", "description": "Secret reference: env:NAME, file:/path/to/token or secret:NAME."},
                        "agent": {"type": "string"},
                        "allowed_users": {"type": "array", "items": {"type": "integer"}},
                        "allowed_chats": {"type": "array", "items": {"type": "integer"}},
                        "enabled": {"type": "boolean"},
                    },
                    "required": [],
                },
            ),
            handler=host_telegram_configure,
        ),
        "host_status": ToolEntry(
            definition=ToolDefinition(
                name="host_status",
                description="Inspect Marius host status: configured agents, gateway state and systemd hints.",
                parameters={
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "description": "Optional agent name to inspect."},
                    },
                    "required": [],
                },
            ),
            handler=host_status,
        ),
        "host_doctor": ToolEntry(
            definition=ToolDefinition(
                name="host_doctor",
                description="Run the Marius installation doctor and return the structured report.",
                parameters={
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "description": "Optional agent name to diagnose."},
                    },
                    "required": [],
                },
            ),
            handler=host_doctor,
        ),
        "host_logs": ToolEntry(
            definition=ToolDefinition(
                name="host_logs",
                description="Read recent Marius diagnostic logs with optional event or agent filters.",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Number of entries to return, max 200."},
                        "event": {"type": "string", "description": "Optional event name filter."},
                        "agent": {"type": "string", "description": "Optional agent filter from log metadata."},
                    },
                    "required": [],
                },
            ),
            handler=host_logs,
        ),
        "host_gateway_restart": ToolEntry(
            definition=ToolDefinition(
                name="host_gateway_restart",
                description="Schedule a safe restart of a Marius gateway after the current answer can be sent.",
                parameters={
                    "type": "object",
                    "properties": {
                        "agent": {"type": "string", "description": "Agent gateway to restart. Defaults to main agent."},
                        "mode": {"type": "string", "description": "auto, direct or systemd."},
                        "delay_seconds": {"type": "number", "description": "Delay before restart, 0.5 to 30 seconds."},
                        "confirm": {"type": "boolean", "description": "Must be true to schedule the restart."},
                    },
                    "required": ["confirm"],
                },
            ),
            handler=host_gateway_restart,
        ),
    }


_DEFAULT_TOOLS = make_host_admin_tools()
HOST_AGENT_LIST = _DEFAULT_TOOLS["host_agent_list"]
HOST_AGENT_SAVE = _DEFAULT_TOOLS["host_agent_save"]
HOST_AGENT_DELETE = _DEFAULT_TOOLS["host_agent_delete"]
HOST_TELEGRAM_CONFIGURE = _DEFAULT_TOOLS["host_telegram_configure"]
HOST_STATUS = _DEFAULT_TOOLS["host_status"]
HOST_DOCTOR = _DEFAULT_TOOLS["host_doctor"]
HOST_LOGS = _DEFAULT_TOOLS["host_logs"]
HOST_GATEWAY_RESTART = _DEFAULT_TOOLS["host_gateway_restart"]


def _agent_status(cfg: MariusConfig, name: str, is_running: StatusRunner) -> dict[str, Any]:
    agent = cfg.agents.get(name)
    if agent is None:
        return {"name": name, "configured": False}
    return {
        "name": name,
        "configured": True,
        "provider_id": agent.provider_id,
        "model": agent.model,
        "role": agent.role,
        "daily_model": agent.daily_model,
        "tool_count": len(agent.tools),
        "tools": list(agent.tools),
        "skill_count": len(agent.skills),
        "skills": list(agent.skills),
        "scheduler_enabled": agent.scheduler_enabled,
        "gateway_running": bool(is_running(name)),
        "systemd_active": _safe_systemd_state(agent_active_state, name),
        "systemd_enabled": _safe_systemd_state(agent_enabled_state, name),
    }


def _agent_config_data(agent: AgentConfig) -> dict[str, Any]:
    return {
        "name": agent.name,
        "provider_id": agent.provider_id,
        "model": agent.model,
        "role": agent.role,
        "daily_model": agent.daily_model,
        "tools": list(agent.tools),
        "skills": list(agent.skills),
        "scheduler_enabled": agent.scheduler_enabled,
    }


def _systemd_status() -> dict[str, Any]:
    return {
        "available": _safe_bool(is_systemd_available),
        "service_installed": _safe_bool(is_service_installed),
    }


def _safe_bool(fn: Callable[[], bool]) -> bool:
    try:
        return bool(fn())
    except Exception:
        return False


def _safe_systemd_state(fn: Callable[[str], str], agent_name: str) -> str:
    try:
        return fn(agent_name)
    except Exception:
        return "unknown"


def _section_data(section: Section) -> dict[str, Any]:
    return {
        "title": section.title,
        "checks": [
            {"label": check.label, "ok": check.ok, "hint": check.hint, "warning": check.warning}
            for check in section.checks
        ],
    }


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "oui", "o", "on")
    return bool(value)


def _optional_hhmm(value: object, default: str) -> str:
    text = _optional_text(value)
    return validate_hhmm(text) if text else default


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _bounded_float(value: object, *, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _matches_log(entry: LogEntry, *, event: str | None, agent: str | None) -> bool:
    if event and entry.event != event:
        return False
    if agent and str(entry.data.get("agent") or "") != agent:
        return False
    return True


def _ensure_config(store: ConfigStore) -> MariusConfig | None:
    return store.load()


def _valid_agent_name(name: str) -> bool:
    return bool(_AGENT_NAME_RE.fullmatch(name))


def _resolve_toolset(base: list[str], arguments: dict[str, Any], *, role: str) -> list[str]:
    raw_tools = arguments.get("tools")
    if raw_tools is None:
        tools = list(base)
    else:
        tools = _string_list(raw_tools)
    tools = _resolve_string_list(tools, arguments, replace_key="", add_key="add_tools", remove_key="remove_tools")
    unknown = [tool for tool in tools if tool not in ALL_TOOLS]
    if unknown:
        raise ValueError(f"Unknown tool(s): {', '.join(unknown)}")
    forbidden = sorted(set(tools).intersection(ADMIN_ONLY_TOOLS)) if role != "admin" else []
    if forbidden:
        raise ValueError(f"Admin-only tool(s) for role '{role}': {', '.join(forbidden)}")
    return effective_tools_for_role([tool for tool in ALL_TOOLS if tool in set(tools)], role)


def _resolve_string_list(base: list[str], arguments: dict[str, Any], *, replace_key: str, add_key: str, remove_key: str) -> list[str]:
    values = _string_list(arguments.get(replace_key)) if replace_key and arguments.get(replace_key) is not None else list(base)
    seen = set(values)
    for item in _string_list(arguments.get(add_key)):
        if item not in seen:
            values.append(item)
            seen.add(item)
    remove = set(_string_list(arguments.get(remove_key)))
    return [item for item in values if item not in remove]


def _string_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _int_list(value: object, default: list[int]) -> list[int]:
    if value is None:
        return list(default)
    if isinstance(value, str):
        raw = [part.strip() for part in value.split(",") if part.strip()]
    elif isinstance(value, list):
        raw = value
    else:
        raw = []
    result: list[int] = []
    for item in raw:
        try:
            result.append(int(item))
        except (TypeError, ValueError):
            continue
    return result


def _read_secret_ref(ref: str | None, *, secret_ref_path: Path | None = None) -> str:
    if not ref:
        return ""
    if ref.startswith("secret:"):
        from marius.storage.secret_ref_store import SecretRefStore
        secret = SecretRefStore(path=secret_ref_path).get(ref[7:].strip())
        if secret is None:
            return ""
        return _read_secret_ref(secret.ref, secret_ref_path=secret_ref_path)
    if ref.startswith("env:"):
        return os.environ.get(ref[4:].strip(), "").strip()
    if ref.startswith("file:"):
        path = Path(ref[5:].strip()).expanduser()
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError:
            return ""
    return ""


def _secret_source_label(ref: str | None) -> str:
    if not ref:
        return ""
    if ref.startswith("env:"):
        return f"env:{ref[4:].strip()}"
    if ref.startswith("file:"):
        return f"file:{Path(ref[5:].strip()).expanduser()}"
    if ref.startswith("secret:"):
        return f"secret:{ref[7:].strip()}"
    return "unsupported"


def _load_telegram_config(path: Path | None) -> TelegramChannelConfig | None:
    if path is None:
        from marius.channels.telegram.config import load
        return load()
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return TelegramChannelConfig(
            token=raw["token"],
            agent_name=raw.get("agent_name", "main"),
            allowed_users=[int(u) for u in raw.get("allowed_users", [])],
            allowed_chats=[int(c) for c in raw.get("allowed_chats", [])],
            enabled=bool(raw.get("enabled", True)),
        )
    except (json.JSONDecodeError, KeyError, TypeError, OSError):
        return None


def _save_telegram_config(cfg: TelegramChannelConfig, path: Path | None) -> None:
    if path is None:
        from marius.channels.telegram.config import save
        save(cfg)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(cfg), indent=2, ensure_ascii=False), encoding="utf-8")
