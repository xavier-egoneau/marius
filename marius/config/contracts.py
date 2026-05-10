"""Contrats de configuration globale de Marius."""

from __future__ import annotations

from dataclasses import dataclass, field

# Outils disponibles dans le registre
ALL_TOOLS: list[str] = [
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
