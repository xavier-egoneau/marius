"""Contrats de configuration globale de Marius."""

from __future__ import annotations

from dataclasses import dataclass, field

ROLE_ADMIN = "admin"
ROLE_AGENT = "agent"

# Outils disponibles dans le registre
ALL_TOOLS: list[str] = [
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
    "host_gateway_restart",
    "project_list",
    "project_set_active",
    "approval_list",
    "approval_decide",
    "approval_forget",
    "secret_ref_list",
    "secret_ref_save",
    "secret_ref_delete",
    "secret_ref_prepare_file",
    "provider_list",
    "provider_save",
    "provider_delete",
    "provider_models",
    "dreaming_run",
    "self_update_propose",
    "self_update_report_bug",
    "self_update_list",
    "self_update_show",
    "self_update_apply",
    "self_update_rollback",
    "open_marius_web",
    "rag_source_add",
    "rag_source_list",
    "rag_source_sync",
    "rag_search",
    "rag_get",
    "rag_promote_to_memory",
    "rag_checklist_add",
    "caldav_doctor",
    "caldav_agenda",
    "caldav_maintenance",
    "sentinelle_scan",
    "spawn_agent",
    "call_agent",
    "task_create",
    "task_list",
    "task_update",
]

# Outils actifs par défaut pour l'admin.
DEFAULT_TOOLS: list[str] = list(ALL_TOOLS)

ADMIN_ONLY_TOOLS: set[str] = {
    "host_agent_save",
    "host_agent_delete",
    "host_telegram_configure",
    "host_gateway_restart",
    "approval_decide",
    "approval_forget",
    "secret_ref_save",
    "secret_ref_delete",
    "secret_ref_prepare_file",
    "provider_save",
    "provider_delete",
    "self_update_apply",
    "self_update_rollback",
}

AGENT_DEFAULT_DISABLED_TOOLS: set[str] = {
    *ADMIN_ONLY_TOOLS,
    "spawn_agent",
    "call_agent",
}

DEFAULT_AGENT_TOOLS: list[str] = [
    tool for tool in ALL_TOOLS
    if tool not in AGENT_DEFAULT_DISABLED_TOOLS
]


def normalize_role(role: str | None) -> str:
    return ROLE_ADMIN if role == ROLE_ADMIN else ROLE_AGENT


def default_tools_for_role(role: str | None) -> list[str]:
    return list(DEFAULT_TOOLS if normalize_role(role) == ROLE_ADMIN else DEFAULT_AGENT_TOOLS)


def effective_tools_for_role(tools: list[str] | None, role: str | None) -> list[str]:
    selected = list(tools) if tools is not None else default_tools_for_role(role)
    if normalize_role(role) == ROLE_ADMIN:
        return selected
    return [tool for tool in selected if tool not in ADMIN_ONLY_TOOLS]


@dataclass
class AgentConfig:
    name: str
    provider_id: str        # référence un ProviderEntry.id
    model: str
    role: str = "agent"          # "admin" | "agent"
    tools: list[str] | None = None
    skills: list[str] = field(default_factory=list)
    scheduler_enabled: bool = True

    def __post_init__(self) -> None:
        self.role = normalize_role(self.role)
        if self.tools is None:
            self.tools = default_tools_for_role(self.role)
        else:
            self.tools = effective_tools_for_role(self.tools, self.role)

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


@dataclass
class MariusConfig:
    permission_mode: str    # "safe" | "limited" | "power"
    main_agent: str         # nom de l'agent principal (premier configuré)
    agents: dict[str, AgentConfig] = field(default_factory=dict)

    # workspace et USER.md appartiennent au skill assistant — pas à la config de base

    def get_main_agent(self) -> AgentConfig | None:
        return self.agents.get(self.main_agent)

    def get_agent(self, name: str) -> AgentConfig | None:
        return self.agents.get(name)
