"""Point d'entrée CLI pour Marius."""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="marius",
        description="Marius — assistant agentique modulaire",
    )
    parser.add_argument(
        "--agent",
        metavar="NOM",
        default=None,
        help="Nom de l'agent à lancer (défaut : agent principal configuré)",
    )

    subs = parser.add_subparsers(dest="command", metavar="commande")

    # marius setup
    subs.add_parser("setup", help="Configurer Marius (first-run ou reconfiguration)")

    # marius config [--agent NOM]
    config_p = subs.add_parser("config", help="Reconfigurer un agent")
    config_p.add_argument("--agent", metavar="NOM", default=None)

    # marius add provider
    add_p = subs.add_parser("add", help="Ajouter une ressource")
    add_sub = add_p.add_subparsers(dest="resource", metavar="ressource")
    add_sub.add_parser("provider", help="Configurer un nouveau provider LLM")

    # marius edit provider
    edit_p = subs.add_parser("edit", help="Modifier une ressource existante")
    edit_sub = edit_p.add_subparsers(dest="resource", metavar="ressource")
    edit_sub.add_parser("provider", help="Modifier un provider LLM configuré")

    # marius set model
    set_p = subs.add_parser("set", help="Changer une valeur active")
    set_sub = set_p.add_subparsers(dest="resource", metavar="ressource")
    set_sub.add_parser("model", help="Changer le modèle actif d'un provider")

    # marius skills [list | activate | deactivate]
    skills_p = subs.add_parser("skills", help="Gérer les skills d'un agent")
    skills_sub = skills_p.add_subparsers(dest="skills_cmd", metavar="action")
    skills_sub.add_parser("list", help="Lister les skills disponibles et leur statut")
    skills_activate = skills_sub.add_parser("activate", help="Activer un skill pour un agent")
    skills_activate.add_argument("skill", metavar="NOM", help="Nom du skill à activer")
    skills_activate.add_argument("--agent", metavar="NOM", default=None, help="Agent cible (défaut : agent principal)")
    skills_deactivate = skills_sub.add_parser("deactivate", help="Désactiver un skill pour un agent")
    skills_deactivate.add_argument("skill", metavar="NOM", help="Nom du skill à désactiver")
    skills_deactivate.add_argument("--agent", metavar="NOM", default=None, help="Agent cible (défaut : agent principal)")

    # marius gateway [start | stop | status]
    gw_p = subs.add_parser("gateway", help="Gérer le gateway (processus persistant)")
    gw_sub = gw_p.add_subparsers(dest="gw_cmd", metavar="action")
    gw_start = gw_sub.add_parser("start", help="Démarrer le gateway")
    gw_start.add_argument("--agent", metavar="NOM", default=None)
    gw_stop = gw_sub.add_parser("stop", help="Arrêter le gateway")
    gw_stop.add_argument("--agent", metavar="NOM", default=None)
    gw_status = gw_sub.add_parser("status", help="Statut du gateway")
    gw_status.add_argument("--agent", metavar="NOM", default=None)

    args = parser.parse_args()

    # ── commandes ─────────────────────────────────────────────────────────────

    if args.command == "setup":
        from marius.config.wizard import run_setup
        run_setup()
        return

    if args.command == "config":
        from marius.config.wizard import run_agent_config
        run_agent_config(agent_name=getattr(args, "agent", None))
        return

    if args.command == "add" and getattr(args, "resource", None) == "provider":
        from marius.provider_config.wizard import run_add_provider
        run_add_provider()
        return

    if args.command == "edit" and getattr(args, "resource", None) == "provider":
        from marius.provider_config.wizard import run_edit_provider
        run_edit_provider()
        return

    if args.command == "set" and getattr(args, "resource", None) == "model":
        from marius.provider_config.wizard import run_set_model
        run_set_model()
        return

    if args.command == "skills":
        _cmd_skills(args)
        return

    if args.command == "gateway":
        _cmd_gateway(args)
        return

    # ── lancement du REPL ─────────────────────────────────────────────────────

    agent_name = getattr(args, "agent", None)
    _launch(agent_name=agent_name)


def _launch(agent_name: str | None = None) -> None:
    """Résout la config et lance le REPL pour l'agent demandé."""
    from rich.console import Console

    from marius.config.store import ConfigStore
    from marius.provider_config.store import ProviderStore

    console = Console(highlight=False)
    config_store = ConfigStore()
    config = config_store.load()

    # ── pas de config → pointer vers marius setup ─────────────────────────────
    if config is None:
        console.print(
            "\n[bold color(208)]Marius n'est pas encore configuré.[/]\n"
            "  Lancez [bold]marius setup[/] pour démarrer.\n"
        )
        sys.exit(1)

    # ── résolution de l'agent ─────────────────────────────────────────────────
    name = agent_name or config.main_agent
    agent_cfg = config.get_agent(name)
    if agent_cfg is None:
        console.print(
            f"\n[bold color(208)]Agent inconnu :[/] {name}\n"
            f"  Agents configurés : {', '.join(config.agents) or 'aucun'}\n"
            f"  Lancez [bold]marius setup[/] ou [bold]marius config --agent {name}[/].\n"
        )
        sys.exit(1)

    # ── résolution du provider ────────────────────────────────────────────────
    provider_store = ProviderStore()
    providers = provider_store.load()
    entry = next((p for p in providers if p.id == agent_cfg.provider_id), None)
    if entry is None and providers:
        entry = providers[0]
    if entry is None:
        console.print(
            "\n[bold color(208)]Aucun provider configuré.[/]\n"
            "  Lancez [bold]marius setup[/] pour configurer un provider.\n"
        )
        sys.exit(1)

    # ── override du modèle depuis la config agent ─────────────────────────────
    if agent_cfg.model and agent_cfg.model != entry.model:
        from dataclasses import replace
        entry = replace(entry, model=agent_cfg.model)

    # ── lancement ─────────────────────────────────────────────────────────────
    if agent_name:
        # Mode gateway : --agent spécifié → connexion au processus persistant
        _launch_gateway(agent_name=name, console=console)
    else:
        # Mode local : REPL classique dans le CWD
        from marius.host.repl import run_repl
        run_repl(
            entry,
            agent_config=agent_cfg,
            permission_mode=config.permission_mode,
        )


def _launch_gateway(agent_name: str, console) -> None:
    """Démarre le gateway si nécessaire puis connecte le client."""
    from marius.gateway.launcher import is_running, start
    from marius.gateway.client import connect_and_run

    if not is_running(agent_name):
        console.print(f"\n[dim]Démarrage du gateway '{agent_name}'…[/]")
        ok = start(agent_name)
        if not ok:
            console.print(
                f"\n[bold color(208)]Impossible de démarrer le gateway '{agent_name}'.[/]\n"
                f"  Vérifiez la config avec [bold]marius setup[/].\n"
            )
            return
        console.print(f"[dim]Gateway prêt.[/]\n")

    connect_and_run(agent_name)


def _cmd_gateway(args) -> None:
    """Gère les sous-commandes `marius gateway`."""
    from rich.console import Console

    from marius.config.store import ConfigStore
    from marius.gateway.launcher import is_running, start, stop

    console = Console(highlight=False)
    gw_cmd = getattr(args, "gw_cmd", None)

    config_store = ConfigStore()
    config = config_store.load()

    def _resolve_agent_name() -> str | None:
        agent_arg = getattr(args, "agent", None)
        if agent_arg:
            return agent_arg
        if config:
            return config.main_agent
        return None

    if gw_cmd == "start" or gw_cmd is None:
        name = _resolve_agent_name()
        if not name:
            console.print("\n[dim]Aucun agent configuré. Lancez marius setup.[/]\n")
            return
        if is_running(name):
            console.print(f"\n[dim]Gateway '{name}' déjà actif.[/]\n")
            return
        console.print(f"\n[dim]Démarrage du gateway '{name}'…[/]")
        ok = start(name)
        if ok:
            console.print(f"[dim]Gateway '{name}' démarré.[/]\n")
        else:
            console.print(f"\n[bold color(208)]Échec du démarrage du gateway '{name}'.[/]\n")
        return

    if gw_cmd == "stop":
        name = _resolve_agent_name()
        if not name:
            console.print("\n[dim]Aucun agent configuré.[/]\n")
            return
        ok = stop(name)
        if ok:
            console.print(f"\n[dim]Gateway '{name}' arrêté.[/]\n")
        else:
            console.print(f"\n[dim]Gateway '{name}' n'était pas actif.[/]\n")
        return

    if gw_cmd == "status":
        if config is None:
            console.print("\n[dim]Aucune configuration trouvée.[/]\n")
            return
        console.print()
        from rich.table import Table
        t = Table.grid(padding=(0, 2))
        t.add_column(style="bold", no_wrap=True)
        t.add_column()
        for agent_name in config.agents:
            running = is_running(agent_name)
            status_label = "[green]actif[/]" if running else "[dim]inactif[/]"
            t.add_row(agent_name, status_label)
        console.print("[bold color(208)]État des gateways[/]\n")
        console.print(t)
        console.print()
        return

    console.print("[dim]Usage : marius gateway [start|stop|status][/]\n")


def _cmd_skills(args) -> None:
    """Gère les sous-commandes `marius skills`."""
    from rich.console import Console
    from rich.table import Table

    from marius.config.store import ConfigStore
    from marius.kernel.skills import SkillReader

    console = Console(highlight=False)
    skills_cmd = getattr(args, "skills_cmd", None)

    # ── list ──────────────────────────────────────────────────────────────────
    if skills_cmd == "list" or skills_cmd is None:
        reader = SkillReader()
        available = reader.list()
        if not available:
            console.print("\n[dim]Aucun skill installé dans ~/.marius/skills/[/]\n")
            return

        config_store = ConfigStore()
        config = config_store.load()
        active_per_agent: dict[str, list[str]] = {}
        if config:
            for agent_name, agent_cfg in config.agents.items():
                for s in agent_cfg.skills:
                    active_per_agent.setdefault(s, []).append(agent_name)

        console.print()
        console.print("[bold color(208)]Skills disponibles[/]\n")
        t = Table.grid(padding=(0, 2))
        t.add_column(style="bold", no_wrap=True)
        t.add_column()
        t.add_column(style="dim")
        t.add_column(style="dim")
        for meta in available:
            agents = active_per_agent.get(meta.name, [])
            status = "[green]actif[/]" if agents else "[dim]inactif[/]"
            agent_label = ", ".join(agents) if agents else ""
            t.add_row(meta.name, meta.description, status, agent_label)
        console.print(t)
        console.print()
        return

    # ── activate / deactivate ─────────────────────────────────────────────────
    if skills_cmd in ("activate", "deactivate"):
        skill_name: str = args.skill
        agent_arg: str | None = getattr(args, "agent", None)

        reader = SkillReader()
        if not reader.exists(skill_name):
            console.print(
                f"\n[bold color(208)]Skill inconnu :[/] {skill_name}\n"
                f"  Lancez [bold]marius skills list[/] pour voir les skills disponibles.\n"
            )
            sys.exit(1)

        config_store = ConfigStore()
        config = config_store.load()
        if config is None:
            console.print(
                "\n[bold color(208)]Marius n'est pas configuré.[/]\n"
                "  Lancez [bold]marius setup[/] pour démarrer.\n"
            )
            sys.exit(1)

        name = agent_arg or config.main_agent
        agent_cfg = config.get_agent(name)
        if agent_cfg is None:
            console.print(
                f"\n[bold color(208)]Agent inconnu :[/] {name}\n"
                f"  Agents configurés : {', '.join(config.agents) or 'aucun'}\n"
            )
            sys.exit(1)

        skills = list(agent_cfg.skills)
        if skills_cmd == "activate":
            if skill_name in skills:
                console.print(f"\n[dim]Skill '{skill_name}' déjà actif pour {name}.[/]\n")
                return
            skills.append(skill_name)
            verb = "activé"
        else:
            if skill_name not in skills:
                console.print(f"\n[dim]Skill '{skill_name}' n'est pas actif pour {name}.[/]\n")
                return
            skills.remove(skill_name)
            verb = "désactivé"

        from dataclasses import replace
        updated_agent = replace(agent_cfg, skills=skills)
        config.agents[name] = updated_agent
        config_store.save(config)
        console.print(f"\n[dim]Skill '{skill_name}' {verb} pour l'agent '{name}'.[/]\n")
        return

    console.print(f"[dim]Action inconnue. Usage : marius skills [list|activate|deactivate][/]\n")
