"""Wizard de configuration Marius (marius setup).

Déclenché à l'installation ou pour reconfigurer.
Conserve les valeurs existantes comme défauts.

Périmètre : provider, environnement, permission, agents.
USER.md et workspace appartiennent au skill assistant.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.text import Text

from marius.config.contracts import (
    ALL_TOOLS,
    AgentConfig,
    MariusConfig,
    default_tools_for_role,
    effective_tools_for_role,
)
from marius.kernel.scheduler import validate_hhmm
from marius.config.store import ConfigStore
from marius.kernel.skills import SkillReader
from marius.provider_config.store import ProviderStore
from marius.provider_config.wizard import run_add_provider

_MARIUS_HOME = Path.home() / ".marius"


def run_setup(console: Console | None = None) -> MariusConfig | None:
    """Lance le wizard de configuration. Retourne la config sauvegardée."""
    c = console or Console(highlight=False)
    store = ConfigStore()
    existing = store.load()

    c.print()
    c.print(Panel(
        Text("Marius — Configuration", style="bold color(208)", justify="center"),
        border_style="dim",
        padding=(0, 2),
    ))
    c.print()

    # ── provider ──────────────────────────────────────────────────────────────

    provider_store = ProviderStore()
    providers = provider_store.load()

    if not providers:
        c.print("[bold]Provider LLM[/]\n")
        c.print("  Aucun provider configuré. Lancement du wizard provider...\n")
        run_add_provider(store=provider_store, console=c)
        providers = provider_store.load()
        if not providers:
            c.print("\n  [dim]Aucun provider configuré. Configuration annulée.[/]\n")
            return None
    else:
        c.print(f"[bold]Provider LLM[/]  [dim]{len(providers)} configuré(s)[/]\n")
        for p in providers:
            c.print(f"  [dim]·[/] {p.name}  [dim]{p.model}[/]")
        c.print()
        raw = c.input("  Reconfigurer un provider ? [[dim]n[/]]: ").strip().lower()
        if raw in ("o", "oui", "y", "yes"):
            run_add_provider(store=provider_store, console=c)
            providers = provider_store.load()

    # ── environnement ─────────────────────────────────────────────────────────

    c.print("\n[bold]Environnement[/]\n")
    _check_environment(c)

    # ── permission ────────────────────────────────────────────────────────────

    current_perm = existing.permission_mode if existing else "limited"
    c.print("\n[bold]Permission par défaut[/]\n")
    c.print("  [color(208)][1][/] Safe    — lecture seule, pas d'extension hors projet")
    c.print("  [color(208)][2][/] Limited — écriture locale, extension explicite [dim](recommandé)[/]")
    c.print("  [color(208)][3][/] Power   — pas de restrictions\n")
    _perm_map = {"safe": "1", "limited": "2", "power": "3"}
    _perm_rev = {"1": "safe", "2": "limited", "3": "power"}
    default_perm = _perm_map.get(current_perm, "2")
    raw = c.input(f"  Choix [[dim]{default_perm}[/]]: ").strip() or default_perm
    permission_mode = _perm_rev.get(raw, "limited")

    # ── agent principal ───────────────────────────────────────────────────────

    existing_agents = existing.agents if existing else {}
    agents: dict[str, AgentConfig] = dict(existing_agents)

    if not agents:
        c.print("\n[bold]Agent admin[/]\n")
        agent_cfg = _configure_agent(
            c, providers=providers, existing=None, default_name="main", role="admin",
        )
        if agent_cfg:
            agents[agent_cfg.name] = agent_cfg
        main_agent = agent_cfg.name if agent_cfg else "main"
    else:
        main_agent = existing.main_agent if existing else next(iter(agents))
        c.print(f"\n[bold]Agents[/]  [dim]{len(agents)} configuré(s), admin : {main_agent}[/]\n")
        for name, ag in agents.items():
            marker = "[color(208)]★[/]" if name == main_agent else " "
            role_label = f"[dim] [{ag.role}][/]" if ag.role else ""
            c.print(f"  {marker} {name}  [dim]{ag.model}[/]{role_label}")
        c.print()
        raw = c.input("  Ajouter un agent ? [[dim]n[/]]: ").strip().lower()
        if raw in ("o", "oui", "y", "yes"):
            agent_cfg = _configure_agent(c, providers=providers, existing=None, role="agent")
            if agent_cfg:
                agents[agent_cfg.name] = agent_cfg

    # ── sauvegarde ────────────────────────────────────────────────────────────

    config = MariusConfig(
        permission_mode=permission_mode,
        main_agent=main_agent,
        agents=agents,
    )
    store.save(config)

    from marius.storage.task_store import seed_agent_system_tasks
    for ag in agents.values():
        seed_agent_system_tasks(ag.name, ag.tools or [])

    c.print()
    c.print("  [dim]✓ Configuration sauvegardée.[/]")
    c.print("  [dim]Lancez[/] [bold]marius[/] [dim]pour démarrer.[/]\n")
    return config


def run_agent_config(
    agent_name: str | None = None,
    console: Console | None = None,
) -> None:
    """Reconfigure un agent existant ou en crée un nouveau."""
    c = console or Console(highlight=False)
    config_store = ConfigStore()
    config = config_store.load()
    if config is None:
        c.print("\n  [dim]Aucune configuration. Lancez[/] marius setup [dim]d'abord.[/]\n")
        return

    provider_store = ProviderStore()
    providers = provider_store.load()
    name = agent_name or config.main_agent
    existing_agent = config.agents.get(name)

    c.print()
    c.print(Panel(
        Text(f"Config agent : {name}", style="bold color(208)", justify="center"),
        border_style="dim", padding=(0, 2),
    ))
    c.print()

    # préserver le role existant si on reconfigure un agent
    existing_role = existing_agent.role if existing_agent else "agent"
    agent_cfg = _configure_agent(
        c, providers=providers, existing=existing_agent, default_name=name, role=existing_role,
    )
    if agent_cfg:
        config.agents[agent_cfg.name] = agent_cfg
        config_store.save(config)
        from marius.storage.task_store import seed_agent_system_tasks
        seed_agent_system_tasks(agent_cfg.name, agent_cfg.tools or [])
        c.print(f"\n  [dim]✓ Agent[/] {agent_cfg.name} [dim]sauvegardé.[/]\n")


# ── helpers ───────────────────────────────────────────────────────────────────


def _configure_agent(
    c: Console,
    *,
    providers: list,
    existing: AgentConfig | None,
    default_name: str = "main",
    role: str = "agent",
) -> AgentConfig | None:
    if not providers:
        c.print("  [dim]Aucun provider disponible.[/]\n")
        return None

    name_default = existing.name if existing else default_name
    name = c.input(f"  Nom [[dim]{name_default}[/]]: ").strip() or name_default

    c.print("\n  Providers disponibles :\n")
    for i, p in enumerate(providers, 1):
        c.print(f"    [color(208)][{i}][/] {p.name}  [dim]{p.provider} · {p.model}[/]")
    c.print()

    default_idx = 1
    if existing:
        for i, p in enumerate(providers, 1):
            if p.id == existing.provider_id:
                default_idx = i
                break
    raw = c.input(f"  Provider [[dim]{default_idx}[/]]: ").strip()
    try:
        selected = providers[int(raw) - 1 if raw else default_idx - 1]
    except (ValueError, IndexError):
        selected = providers[0]

    model_default = existing.model if existing else selected.model
    model = c.input(f"  Modèle [[dim]{model_default}[/]]: ").strip() or model_default

    # ── tools ─────────────────────────────────────────────────────────────────
    available_tools = default_tools_for_role(role)
    current_tools = set(
        effective_tools_for_role(existing.tools, role)
        if existing
        else available_tools
    )
    c.print("\n  Tools actifs :\n")
    for i, tool in enumerate(available_tools, 1):
        mark = "[green]✓[/]" if tool in current_tools else "[dim]○[/]"
        c.print(f"    [color(208)][{i:2}][/] {mark} {tool}")
    c.print()
    active_tool_idx = ", ".join(
        str(i) for i, t in enumerate(available_tools, 1) if t in current_tools
    )
    raw = c.input(f"  Numéros actifs [[dim]{active_tool_idx}[/]]: ").strip()
    if raw:
        chosen = {s.strip() for s in raw.split(",")}
        new_tools = [
            available_tools[int(n) - 1]
            for n in chosen
            if n.isdigit() and 1 <= int(n) <= len(available_tools)
        ]
        new_tools = [t for t in available_tools if t in set(new_tools)]   # ordre canonique
    else:
        new_tools = [t for t in available_tools if t in current_tools]

    # ── skills ────────────────────────────────────────────────────────────────
    skills_default = list(existing.skills) if existing else []
    available_skills = SkillReader().list()
    skills = list(skills_default)
    if available_skills:
        skill_names = [m.name for m in available_skills]
        active_s = set(skills_default)

        # Si assistant est actif, onboarding est inclus par défaut
        from marius.kernel.posture import ASSISTANT_SKILL
        if ASSISTANT_SKILL in active_s and "onboarding" in skill_names:
            active_s.add("onboarding")

        c.print("\n  Skills disponibles :\n")
        for i, meta in enumerate(available_skills, 1):
            mark = "[green]✓[/]" if meta.name in active_s else "[dim]○[/]"
            c.print(f"    [color(208)][{i:2}][/] {mark} {meta.name}  [dim]{meta.description}[/]")
        c.print()
        active_skill_idx = ", ".join(
            str(i) for i, m in enumerate(available_skills, 1) if m.name in active_s
        ) or "aucun"
        raw_s = c.input(f"  Numéros actifs [[dim]{active_skill_idx}[/]]: ").strip()
        if raw_s:
            chosen_s = {s.strip() for s in raw_s.split(",")}
            skills = [
                available_skills[int(n) - 1].name
                for n in chosen_s
                if n.isdigit() and 1 <= int(n) <= len(available_skills)
            ]

    # Scheduler — affiché seulement si le skill assistant est actif
    from marius.kernel.posture import ASSISTANT_SKILL
    prev_skills   = set(existing.skills if existing else [])
    assistant_new = ASSISTANT_SKILL in set(skills) and ASSISTANT_SKILL not in prev_skills
    # Si assistant vient d'être activé → scheduler ON par défaut
    if assistant_new:
        scheduler_enabled = True
    else:
        scheduler_enabled = getattr(existing, "scheduler_enabled", True)

    if ASSISTANT_SKILL in set(skills):
        c.print("\n  [bold]Scheduler[/]  [dim](dreaming — les autres routines se configurent dans Routines)[/]\n")
        raw_enabled = c.input(
            f"  Activer le scheduler ? [[dim]{'O' if scheduler_enabled else 'n'}[/]]: "
        ).strip().lower()
        if raw_enabled:
            scheduler_enabled = raw_enabled in ("o", "oui", "y", "yes", "1", "true")

    return AgentConfig(
        name=name,
        provider_id=selected.id,
        model=model,
        role=role,
        tools=new_tools,
        skills=skills,
        scheduler_enabled=scheduler_enabled,
    )


def _apply_tool_changes(tools: list[str], raw: str) -> list[str]:
    if not raw.strip():
        return tools
    result = set(tools)
    for token in raw.split():
        if token.startswith("+"):
            t = token[1:]
            if t in ALL_TOOLS:
                result.add(t)
        elif token.startswith("-"):
            result.discard(token[1:])
    return [t for t in ALL_TOOLS if t in result]


def _check_environment(c: Console) -> None:
    docker_ok = _command_exists("docker")
    _status_line(c, "Docker", docker_ok, "non trouvé — web_search nécessite Docker")

    if not docker_ok:
        return

    searxng_url = os.environ.get("MARIUS_SEARCH_URL", "http://localhost:19080")
    searxng_ok = _check_url(searxng_url)
    _status_line(c, f"SearxNG ({searxng_url})", searxng_ok, "non démarré")

    if not searxng_ok:
        compose_file = Path(__file__).parents[3] / "docker-compose.searxng.yml"
        if compose_file.exists():
            raw = c.input("\n  Démarrer SearxNG ? [[dim]O/n[/]]: ").strip().lower()
            if raw in ("", "o", "oui", "y", "yes"):
                try:
                    subprocess.run(
                        ["docker", "compose", "-f", str(compose_file), "up", "-d"],
                        check=True, capture_output=True,
                    )
                    _status_line(c, "SearxNG", True)
                except subprocess.CalledProcessError:
                    c.print("  [dim]Échec du démarrage SearxNG.[/]")


def _status_line(c: Console, label: str, ok: bool, hint: str = "") -> None:
    mark = "[green]✓[/]" if ok else "[dim]✗[/]"
    suffix = f"  [dim]{hint}[/]" if not ok and hint else ""
    c.print(f"  {mark} {label}{suffix}")


def _command_exists(cmd: str) -> bool:
    from marius.config.checks import command_exists
    return command_exists(cmd)


def _check_url(url: str) -> bool:
    from marius.config.checks import check_url
    return check_url(url)
