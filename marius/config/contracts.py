"""Contrats de configuration globale de Marius."""

from __future__ import annotations

from dataclasses import dataclass, field

from marius.tools.factory import registered_tool_names

ROLE_ADMIN = "admin"
ROLE_AGENT = "agent"

# Outils disponibles dans le registre runtime. La source de vérité est la factory.
ALL_TOOLS: list[str] = registered_tool_names()

TOOL_GROUPS: list[dict[str, object]] = [
    {
        "id": "filesystem",
        "label": "Filesystem",
        "description": "Lecture, écriture et déplacement de fichiers",
        "tools": ["read_file", "list_dir", "write_file", "make_dir", "move_path"],
    },
    {
        "id": "explore",
        "label": "Explore",
        "description": "Parcours et recherche dans l'arborescence",
        "prefixes": ["explore_"],
    },
    {
        "id": "shell",
        "label": "Shell",
        "description": "Exécution de commandes shell",
        "tools": ["run_bash"],
    },
    {
        "id": "web",
        "label": "Web",
        "description": "Recherche web et récupération de pages",
        "prefixes": ["web_"],
    },
    {
        "id": "browser",
        "label": "Browser",
        "description": "Contrôle navigateur Playwright pour pages dynamiques et interactions web",
        "prefixes": ["browser_"],
    },
    {
        "id": "vision",
        "label": "Vision",
        "description": "Analyse d'images locales via Ollama",
        "tools": ["vision"],
    },
    {
        "id": "skill_authoring",
        "label": "Skill authoring",
        "description": "Lire, créer et recharger des fichiers de skills (authoring uniquement)",
        "prefixes": ["skill_"],
    },
    {
        "id": "host",
        "label": "Host",
        "description": "Permissions pour interroger Marius lui-même : lister les agents, lire les logs, diagnostics, redémarrer le gateway",
        "prefixes": ["host_"],
    },
    {
        "id": "projects",
        "label": "Projects",
        "description": "Gestion et sélection du projet actif",
        "prefixes": ["project_"],
    },
    {
        "id": "security",
        "label": "Security",
        "description": "Permissions pour gérer les approbations d'actions et les références de secrets (pas les secrets eux-mêmes)",
        "prefixes": ["approval_", "secret_ref_"],
    },
    {
        "id": "provider",
        "label": "Provider",
        "description": "Permissions pour lister ou modifier les providers LLM configurés",
        "prefixes": ["provider_"],
    },
    {
        "id": "tasks_routines",
        "label": "Tasks / Routines",
        "description": "Créer, lister et mettre à jour les tâches uniques et les routines récurrentes",
        "tools": ["task_create", "task_list", "task_update"],
    },
    {
        "id": "reminders",
        "label": "Reminders",
        "description": "Créer, lister et annuler des rappels personnels",
        "tools": ["reminders"],
    },
    {
        "id": "dreaming",
        "label": "Dreaming",
        "description": "Déclencher manuellement la consolidation mémoire",
        "tools": ["dreaming_run"],
    },
    {
        "id": "self_update",
        "label": "Self-update",
        "description": "Permissions pour proposer, appliquer ou rollback des mises à jour de Marius",
        "prefixes": ["self_update_"],
    },
    {
        "id": "watch",
        "label": "Watch",
        "description": "Veille automatisée sur des sujets web",
        "prefixes": ["watch_"],
    },
    {
        "id": "rag",
        "label": "RAG",
        "description": "Sources Markdown indexées, recherche sémantique, checklists",
        "prefixes": ["rag_"],
    },
    {
        "id": "calendar",
        "label": "Calendar",
        "description": "Calendrier CalDAV via khal/vdirsyncer",
        "prefixes": ["caldav_"],
    },
    {
        "id": "sentinelle",
        "label": "Sentinelle",
        "description": "Audit local : ports ouverts, services, Docker, dérive système",
        "tools": ["sentinelle_scan"],
    },
    {
        "id": "agents",
        "label": "Agents",
        "description": "Délégation de tâches parallèles à des sous-agents ou agents nommés",
        "tools": ["spawn_agent", "call_agent"],
    },
    {
        "id": "web_ui",
        "label": "Web UI",
        "description": "Ouverture de l'interface web Marius",
        "tools": ["open_marius_web"],
    },
]


def resolved_tool_groups(tools: list[str] | None = None) -> list[dict[str, object]]:
    available = list(tools or ALL_TOOLS)
    available_set = set(available)
    seen: set[str] = set()
    groups: list[dict[str, object]] = []

    for group in TOOL_GROUPS:
        items: list[str] = []
        for tool in group.get("tools", []):
            if isinstance(tool, str) and tool in available_set and tool not in items:
                items.append(tool)
        for prefix in group.get("prefixes", []):
            if not isinstance(prefix, str):
                continue
            for tool in available:
                if tool.startswith(prefix) and tool not in items:
                    items.append(tool)
        if not items:
            continue
        seen.update(items)
        groups.append({
            "id": group["id"],
            "label": group["label"],
            "description": group.get("description", ""),
            "tools": items,
        })

    other = [tool for tool in available if tool not in seen]
    if other:
        groups.append({
            "id": "other",
            "label": "Other",
            "description": "Outils non classés explicitement",
            "tools": other,
        })
    return groups

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

AGENT_INITIAL_DISABLED_TOOLS: set[str] = {
    "spawn_agent",
    "call_agent",
}

SKILL_GATED_TOOLS: set[str] = {
    "browser_open",
    "browser_extract",
    "browser_screenshot",
    "browser_click",
    "browser_type",
    "browser_close",
}

AGENT_DEFAULT_DISABLED_TOOLS: set[str] = {
    *ADMIN_ONLY_TOOLS,
    *AGENT_INITIAL_DISABLED_TOOLS,
    *SKILL_GATED_TOOLS,
}

SKILL_REQUIRED_TOOLS: dict[str, list[str]] = {
    "kanban": ["task_create", "task_list", "task_update"],
    "browser": [
        "browser_open",
        "browser_extract",
        "browser_screenshot",
        "browser_click",
        "browser_type",
        "browser_close",
    ],
}


def normalize_role(role: str | None) -> str:
    return ROLE_ADMIN if role == ROLE_ADMIN else ROLE_AGENT


def default_tools_for_role(role: str | None) -> list[str]:
    return effective_tools_from_disabled(default_disabled_tools_for_role(role), role)


def allowed_tools_for_role(role: str | None) -> list[str]:
    if normalize_role(role) == ROLE_ADMIN:
        return list(DEFAULT_TOOLS)
    return [tool for tool in ALL_TOOLS if tool not in ADMIN_ONLY_TOOLS]


def default_disabled_tools_for_role(role: str | None) -> list[str]:
    if normalize_role(role) == ROLE_ADMIN:
        return [tool for tool in ALL_TOOLS if tool in SKILL_GATED_TOOLS]
    return [tool for tool in ALL_TOOLS if tool in AGENT_INITIAL_DISABLED_TOOLS or tool in SKILL_GATED_TOOLS]


def effective_tools_for_role(tools: list[str] | None, role: str | None) -> list[str]:
    selected = list(tools) if tools is not None else default_tools_for_role(role)
    if normalize_role(role) == ROLE_ADMIN:
        return selected
    return [tool for tool in selected if tool not in ADMIN_ONLY_TOOLS]


def effective_tools_from_disabled(disabled_tools: list[str] | None, role: str | None) -> list[str]:
    disabled = set(disabled_tools or [])
    return [tool for tool in allowed_tools_for_role(role) if tool not in disabled]


def disabled_tools_for_active_tools(active_tools: list[str] | None, role: str | None) -> list[str]:
    active = set(effective_tools_for_role(active_tools, role))
    return [tool for tool in allowed_tools_for_role(role) if tool not in active]


def normalize_disabled_tools(
    disabled_tools: list[str] | None,
    role: str | None,
    skills: list[str] | None = None,
) -> list[str]:
    disabled = {str(tool) for tool in disabled_tools or []}
    required = {
        tool
        for skill in skills or []
        for tool in SKILL_REQUIRED_TOOLS.get(skill, [])
    }
    disabled.update(tool for tool in SKILL_GATED_TOOLS if tool not in required)
    return [
        tool
        for tool in allowed_tools_for_role(role)
        if tool in disabled and tool not in required
    ]


def effective_tools_for_agent(
    disabled_tools: list[str] | None,
    role: str | None,
    skills: list[str] | None,
) -> list[str]:
    disabled = normalize_disabled_tools(disabled_tools, role, skills)
    selected = effective_tools_from_disabled(disabled, role)
    selected_set = set(selected)
    for skill in skills or []:
        for tool in SKILL_REQUIRED_TOOLS.get(skill, []):
            if tool in ADMIN_ONLY_TOOLS and normalize_role(role) != ROLE_ADMIN:
                continue
            if tool not in selected_set:
                selected.append(tool)
                selected_set.add(tool)
    return selected


DEFAULT_AGENT_TOOLS: list[str] = default_tools_for_role(ROLE_AGENT)


@dataclass
class AgentConfig:
    name: str
    provider_id: str        # référence un ProviderEntry.id
    model: str
    role: str = "agent"          # "admin" | "agent"
    tools: list[str] | None = None
    disabled_tools: list[str] | None = None
    skills: list[str] = field(default_factory=list)
    scheduler_enabled: bool = True
    permission_mode: str = "limited"  # "safe" | "limited" | "power"

    def __post_init__(self) -> None:
        self.role = normalize_role(self.role)
        if self.disabled_tools is None:
            if self.tools is None:
                self.disabled_tools = default_disabled_tools_for_role(self.role)
            else:
                self.disabled_tools = normalize_disabled_tools(
                    disabled_tools_for_active_tools(self.tools, self.role),
                    self.role,
                    self.skills,
                )
        else:
            self.disabled_tools = normalize_disabled_tools(self.disabled_tools, self.role, self.skills)
        self.tools = effective_tools_for_agent(self.disabled_tools, self.role, self.skills)

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
