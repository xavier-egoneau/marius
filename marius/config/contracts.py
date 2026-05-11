"""Contrats de configuration globale de Marius."""

from __future__ import annotations

from dataclasses import dataclass, field

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
    "daily_digest",
    "self_update_propose",
    "self_update_report_bug",
    "self_update_list",
    "self_update_show",
    "self_update_apply",
    "self_update_rollback",
    "watch_add",
    "watch_list",
    "watch_remove",
    "watch_run",
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
]

# Outils actifs par défaut pour un nouvel agent
DEFAULT_TOOLS: list[str] = list(ALL_TOOLS)


@dataclass
class AgentConfig:
    name: str
    provider_id: str        # référence un ProviderEntry.id
    model: str
    tools: list[str] = field(default_factory=lambda: list(DEFAULT_TOOLS))
    skills: list[str] = field(default_factory=list)
    dream_time: str = "02:00"        # HH:MM UTC — vide = désactivé
    daily_time: str = "08:00"        # HH:MM UTC — vide = désactivé
    scheduler_enabled: bool = True


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
