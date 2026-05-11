"""Lecture et écriture de ~/.marius/config.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import AgentConfig, DEFAULT_TOOLS, MariusConfig

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
_PRE_WATCH_DEFAULT_TOOLS = [
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
    "watch_add",
    "watch_list",
    "watch_remove",
    "watch_run",
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
    "watch_add",
    "watch_list",
    "watch_remove",
    "watch_run",
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
    "watch_add",
    "watch_list",
    "watch_remove",
    "watch_run",
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
    "watch_add",
    "watch_list",
    "watch_remove",
    "watch_run",
    "open_marius_web",
    "spawn_agent",
]
_SELF_UPDATE_INDEX = _PRE_DREAMING_TOOLS_DEFAULT_TOOLS.index("self_update_propose")
_PRE_HOST_RESTART_SECRET_FILE_DEFAULT_TOOLS = [
    *_PRE_DREAMING_TOOLS_DEFAULT_TOOLS[:_SELF_UPDATE_INDEX],
    "dreaming_run",
    "daily_digest",
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
                "daily_model": agent.daily_model,
                "tools": agent.tools,
                "skills": agent.skills,
                "dream_time": agent.dream_time,
                "daily_time": agent.daily_time,
                "scheduler_enabled": agent.scheduler_enabled,
            }
            for name, agent in config.agents.items()
        },
    }


def _from_dict(raw: dict[str, Any]) -> MariusConfig:
    agents = {
        name: AgentConfig(
            name=data["name"],
            provider_id=data["provider_id"],
            model=data["model"],
            daily_model=data.get("daily_model", ""),
            tools=_normalize_tools(data.get("tools")),
            skills=data.get("skills", []),
            dream_time=data.get("dream_time", "02:00"),
            daily_time=data.get("daily_time", "08:00"),
            scheduler_enabled=bool(data.get("scheduler_enabled", True)),
        )
        for name, data in raw.get("agents", {}).items()
    }
    return MariusConfig(
        permission_mode=raw.get("permission_mode", "limited"),
        main_agent=raw.get("main_agent", "main"),
        agents=agents,
    )


def _normalize_tools(raw_tools: Any) -> list[str]:
    if not isinstance(raw_tools, list):
        return list(DEFAULT_TOOLS)
    tools = [str(tool) for tool in raw_tools]
    if tools in (
        _PRE_VISION_DEFAULT_TOOLS,
        _PRE_MARIUS_WEB_DEFAULT_TOOLS,
        _PRE_FILESYSTEM_COMPLETION_DEFAULT_TOOLS,
        _PRE_EXPLORE_DEFAULT_TOOLS,
        _PRE_SKILL_AUTHORING_DEFAULT_TOOLS,
        _PRE_HOST_ADMIN_DEFAULT_TOOLS,
        _PRE_HOST_ACTIONS_DEFAULT_TOOLS,
        _PRE_SELF_UPDATE_DEFAULT_TOOLS,
        _PRE_WATCH_DEFAULT_TOOLS,
        _PRE_PROJECT_DEFAULT_TOOLS,
        _PRE_SECURITY_DEFAULT_TOOLS,
        _PRE_PROVIDER_ADMIN_DEFAULT_TOOLS,
        _PRE_DREAMING_TOOLS_DEFAULT_TOOLS,
        _PRE_HOST_RESTART_SECRET_FILE_DEFAULT_TOOLS,
        _PRE_SELF_UPDATE_APPLY_DEFAULT_TOOLS,
        _PRE_HOST_RESTART_SECRET_FILE_SELF_UPDATE_APPLY_DEFAULT_TOOLS,
        _PRE_RAG_DEFAULT_TOOLS,
    ):
        return list(DEFAULT_TOOLS)
    return tools
