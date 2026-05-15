"""Lecture et écriture de ~/.marius/config.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import (
    DEFAULT_TOOLS,
    SKILL_GATED_TOOLS,
    AgentConfig,
    MariusConfig,
    disabled_tools_for_active_tools,
    default_tools_for_role,
    normalize_disabled_tools,
)

_MARIUS_HOME = Path.home() / ".marius"
DEFAULT_CONFIG_PATH = _MARIUS_HOME / "config.json"
_PRE_VISION_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "run_bash",
    "web_fetch",
    "web_search",
    "skill_view",
]
_PRE_MARIUS_WEB_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "spawn_agent",
]
_PRE_FILESYSTEM_COMPLETION_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "open_marius_web",
    "spawn_agent",
]
_PRE_EXPLORE_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "make_dir",
    "move_path",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "open_marius_web",
    "spawn_agent",
]
_PRE_SKILL_AUTHORING_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "make_dir",
    "move_path",
    "explore_tree",
    "explore_grep",
    "explore_summary",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "open_marius_web",
    "spawn_agent",
]
_PRE_HOST_ADMIN_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "make_dir",
    "move_path",
    "explore_tree",
    "explore_grep",
    "explore_summary",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "skill_create",
    "skill_list",
    "skill_reload",
    "open_marius_web",
    "spawn_agent",
]
_PRE_HOST_ACTIONS_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "make_dir",
    "move_path",
    "explore_tree",
    "explore_grep",
    "explore_summary",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "skill_create",
    "skill_list",
    "skill_reload",
    "host_status",
    "host_doctor",
    "host_logs",
    "open_marius_web",
    "spawn_agent",
]
_PRE_SELF_UPDATE_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "make_dir",
    "move_path",
    "explore_tree",
    "explore_grep",
    "explore_summary",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "skill_create",
    "skill_list",
    "skill_reload",
    "host_agent_list",
    "host_agent_save",
    "host_agent_delete",
    "host_telegram_configure",
    "host_status",
    "host_doctor",
    "host_logs",
    "open_marius_web",
    "spawn_agent",
]
_PRE_PROJECT_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "make_dir",
    "move_path",
    "explore_tree",
    "explore_grep",
    "explore_summary",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "skill_create",
    "skill_list",
    "skill_reload",
    "host_agent_list",
    "host_agent_save",
    "host_agent_delete",
    "host_telegram_configure",
    "host_status",
    "host_doctor",
    "host_logs",
    "self_update_propose",
    "self_update_report_bug",
    "self_update_list",
    "self_update_show",
    "open_marius_web",
    "spawn_agent",
]
_PRE_SECURITY_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "make_dir",
    "move_path",
    "explore_tree",
    "explore_grep",
    "explore_summary",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "skill_create",
    "skill_list",
    "skill_reload",
    "host_agent_list",
    "host_agent_save",
    "host_agent_delete",
    "host_telegram_configure",
    "host_status",
    "host_doctor",
    "host_logs",
    "project_list",
    "project_set_active",
    "self_update_propose",
    "self_update_report_bug",
    "self_update_list",
    "self_update_show",
    "open_marius_web",
    "spawn_agent",
]
_PRE_PROVIDER_ADMIN_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "make_dir",
    "move_path",
    "explore_tree",
    "explore_grep",
    "explore_summary",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "skill_create",
    "skill_list",
    "skill_reload",
    "host_agent_list",
    "host_agent_save",
    "host_agent_delete",
    "host_telegram_configure",
    "host_status",
    "host_doctor",
    "host_logs",
    "project_list",
    "project_set_active",
    "approval_list",
    "approval_decide",
    "approval_forget",
    "secret_ref_list",
    "secret_ref_save",
    "secret_ref_delete",
    "self_update_propose",
    "self_update_report_bug",
    "self_update_list",
    "self_update_show",
    "open_marius_web",
    "spawn_agent",
]
_PRE_DREAMING_TOOLS_DEFAULT_TOOLS = [
    "read_file",
    "list_dir",
    "write_file",
    "make_dir",
    "move_path",
    "explore_tree",
    "explore_grep",
    "explore_summary",
    "run_bash",
    "web_fetch",
    "web_search",
    "vision",
    "skill_view",
    "skill_create",
    "skill_list",
    "skill_reload",
    "host_agent_list",
    "host_agent_save",
    "host_agent_delete",
    "host_telegram_configure",
    "host_status",
    "host_doctor",
    "host_logs",
    "project_list",
    "project_set_active",
    "approval_list",
    "approval_decide",
    "approval_forget",
    "secret_ref_list",
    "secret_ref_save",
    "secret_ref_delete",
    "provider_list",
    "provider_save",
    "provider_delete",
    "provider_models",
    "self_update_propose",
    "self_update_report_bug",
    "self_update_list",
    "self_update_show",
    "open_marius_web",
    "spawn_agent",
]
_SELF_UPDATE_INDEX = _PRE_DREAMING_TOOLS_DEFAULT_TOOLS.index("self_update_propose")
_PRE_HOST_RESTART_SECRET_FILE_DEFAULT_TOOLS = [
    *_PRE_DREAMING_TOOLS_DEFAULT_TOOLS[:_SELF_UPDATE_INDEX],
    "dreaming_run",
    *_PRE_DREAMING_TOOLS_DEFAULT_TOOLS[_SELF_UPDATE_INDEX:],
]
_PRE_SELF_UPDATE_APPLY_DEFAULT_TOOLS = [
    tool for tool in DEFAULT_TOOLS
    if tool not in ("self_update_apply", "self_update_rollback")
]
_PRE_HOST_RESTART_SECRET_FILE_SELF_UPDATE_APPLY_DEFAULT_TOOLS = [
    tool for tool in DEFAULT_TOOLS
    if tool not in (
        "host_gateway_restart",
        "secret_ref_prepare_file",
        "self_update_apply",
        "self_update_rollback",
    )
]
_PRE_RAG_DEFAULT_TOOLS = [
    tool for tool in DEFAULT_TOOLS
    if not tool.startswith("rag_")
]


class ConfigStore:
    def __init__(self, path: Path = DEFAULT_CONFIG_PATH) -> None:
        self.path = path

    def exists(self) -> bool:
        return self.path.exists()

    def load(self) -> MariusConfig | None:
        if not self.path.exists():
            return None
        try:
            raw: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
            return _from_dict(raw)
        except (json.JSONDecodeError, KeyError, TypeError):
            return None

    def save(self, config: MariusConfig) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(_to_dict(config), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )


def _to_dict(config: MariusConfig) -> dict[str, Any]:
    return {
        "permission_mode": config.permission_mode,
        "main_agent": config.main_agent,
        "agents": {
            name: {
                "name": agent.name,
                "provider_id": agent.provider_id,
                "model": agent.model,
                "role": agent.role,
                "disabled_tools": list(agent.disabled_tools or []),
                "skills": agent.skills,
                "scheduler_enabled": agent.scheduler_enabled,
                "permission_mode": agent.permission_mode,
            }
            for name, agent in config.agents.items()
        },
    }


def _from_dict(raw: dict[str, Any]) -> MariusConfig:
    agents: dict[str, AgentConfig] = {}
    for name, data in raw.get("agents", {}).items():
        role = data.get("role") or ("admin" if name == raw.get("main_agent") else "agent")
        agents[name] = AgentConfig(
            name=data["name"],
            provider_id=data["provider_id"],
            model=data["model"],
            # migration : si role absent, l'agent principal est admin
            role=role,
            tools=None,
            disabled_tools=_normalize_disabled_tools(
                data.get("disabled_tools"),
                data.get("tools"),
                role=role,
            ),
            skills=data.get("skills", []),
            scheduler_enabled=bool(data.get("scheduler_enabled", True)),
            permission_mode=data.get("permission_mode", raw.get("permission_mode", "limited")),
        )
    return MariusConfig(
        permission_mode=raw.get("permission_mode", "limited"),
        main_agent=raw.get("main_agent", "main"),
        agents=agents,
    )


def _normalize_disabled_tools(raw_disabled: Any, raw_tools: Any, *, role: str) -> list[str]:
    if isinstance(raw_disabled, list):
        return normalize_disabled_tools([str(tool) for tool in raw_disabled], role)
    if not isinstance(raw_tools, list):
        return disabled_tools_for_active_tools(default_tools_for_role(role), role)
    tools = [str(tool) for tool in raw_tools]
    if _is_default_like_toolset(tools, role):
        return disabled_tools_for_active_tools(default_tools_for_role(role), role)
    return disabled_tools_for_active_tools(tools, role)


def _is_default_like_toolset(tools: list[str], role: str) -> bool:
    if tools in (
        DEFAULT_TOOLS,
        _PRE_VISION_DEFAULT_TOOLS,
        _PRE_MARIUS_WEB_DEFAULT_TOOLS,
        _PRE_FILESYSTEM_COMPLETION_DEFAULT_TOOLS,
        _PRE_EXPLORE_DEFAULT_TOOLS,
        _PRE_SKILL_AUTHORING_DEFAULT_TOOLS,
        _PRE_HOST_ADMIN_DEFAULT_TOOLS,
        _PRE_HOST_ACTIONS_DEFAULT_TOOLS,
        _PRE_SELF_UPDATE_DEFAULT_TOOLS,
        _PRE_PROJECT_DEFAULT_TOOLS,
        _PRE_SECURITY_DEFAULT_TOOLS,
        _PRE_PROVIDER_ADMIN_DEFAULT_TOOLS,
        _PRE_DREAMING_TOOLS_DEFAULT_TOOLS,
        _PRE_HOST_RESTART_SECRET_FILE_DEFAULT_TOOLS,
        _PRE_SELF_UPDATE_APPLY_DEFAULT_TOOLS,
        _PRE_HOST_RESTART_SECRET_FILE_SELF_UPDATE_APPLY_DEFAULT_TOOLS,
        _PRE_RAG_DEFAULT_TOOLS,
    ):
        return True
    default = default_tools_for_role(role)
    if not tools:
        return False
    selected = set(tools) - set(SKILL_GATED_TOOLS)
    default_set = set(default)
    if not selected <= default_set:
        return False
    return len(selected) >= max(20, int(len(default) * 0.75))
