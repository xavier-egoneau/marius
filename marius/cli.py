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

    # marius logs
    logs_p = subs.add_parser("logs", help="Afficher le journal local de diagnostic")
    logs_p.add_argument("--tail", metavar="N", type=int, default=80, help="Nombre d'entrées à afficher")
    logs_p.add_argument("--path", action="store_true", help="Afficher le chemin du fichier de logs")
    logs_p.add_argument("--clear", action="store_true", help="Vider le journal local")

    # marius config [show | tool | --agent NOM]
    config_p = subs.add_parser("config", help="Reconfigurer un agent")
    config_p.add_argument("--agent", metavar="NOM", default=None)
    config_sub = config_p.add_subparsers(dest="config_cmd", metavar="action")

    config_show = config_sub.add_parser("show", help="Afficher la configuration courante")
    config_show.add_argument("--agent", metavar="NOM", default=None)

    config_tool = config_sub.add_parser("tool", help="Activer/désactiver un tool  (+nom / -nom)")
    config_tool.add_argument("change", metavar="+NOM|-NOM", help="Ex: +web_search ou -run_bash")
    config_tool.add_argument("--agent", metavar="NOM", default=None)

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

    # marius telegram [setup | status]
    tg_p = subs.add_parser("telegram", help="Configurer le canal Telegram")
    tg_sub = tg_p.add_subparsers(dest="tg_cmd", metavar="action")
    tg_sub.add_parser("setup",  help="Wizard de configuration du bot Telegram")
    tg_sub.add_parser("status", help="Statut du canal Telegram")

    # marius doctor
    doctor_p = subs.add_parser("doctor", help="Diagnostic de l'installation")
    doctor_p.add_argument("--agent", metavar="NOM", default=None, help="Agent à diagnostiquer")

    # marius web [--port N] — alias pour gateway start --web-port
    web_p = subs.add_parser("web", help="Démarrer le gateway avec le canal web activé")
    web_p.add_argument("--agent", metavar="NOM", default=None)
    web_p.add_argument("--port", metavar="PORT", type=int, default=8765,
                       help="Port HTTP (défaut : 8765)")

    # marius gateway [start | stop | status | install-service | enable | disable]
    gw_p = subs.add_parser("gateway", help="Gérer le gateway (processus persistant)")
    gw_sub = gw_p.add_subparsers(dest="gw_cmd", metavar="action")
    gw_start = gw_sub.add_parser("start", help="Démarrer le gateway manuellement")
    gw_start.add_argument("--agent", metavar="NOM", default=None)
    gw_stop = gw_sub.add_parser("stop", help="Arrêter le gateway")
    gw_stop.add_argument("--agent", metavar="NOM", default=None)
    gw_status = gw_sub.add_parser("status", help="Statut du gateway")
    gw_status.add_argument("--agent", metavar="NOM", default=None)
    gw_sub.add_parser("install-service", help="Installer le service systemd user")
    gw_sub.add_parser("uninstall-service", help="Désinstaller le service systemd user")
    gw_enable = gw_sub.add_parser("enable", help="Activer le gateway au démarrage de session")
    gw_enable.add_argument("--agent", metavar="NOM", default=None)
    gw_disable = gw_sub.add_parser("disable", help="Désactiver le gateway au démarrage")
    gw_disable.add_argument("--agent", metavar="NOM", default=None)

    args = parser.parse_args()

    # ── commandes ─────────────────────────────────────────────────────────────

    if args.command == "doctor":
        from marius.config.doctor import print_report, run_doctor
        agent_arg = getattr(args, "agent", None)
        sections = run_doctor(agent_arg)
        errors = print_report(sections)
        sys.exit(1 if errors else 0)

    if args.command == "setup":
        from marius.config.wizard import run_setup
        run_setup()
        return

    if args.command == "logs":
        _cmd_logs(args)
        return

    if args.command == "config":
        config_cmd = getattr(args, "config_cmd", None)
        agent_arg  = getattr(args, "agent", None)
        if config_cmd == "show":
            _cmd_config_show(getattr(args, "agent", None))
        elif config_cmd == "tool":
            _cmd_config_tool(args.change, agent_arg)
        else:
            from marius.config.wizard import run_agent_config
            run_agent_config(agent_name=agent_arg)
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

    if args.command == "telegram":
        _cmd_telegram(args)
        return

    if args.command == "gateway":
        _cmd_gateway(args)
        return

    if args.command == "web":
        _cmd_web(args)
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
        # Mode gateway — nécessite le skill assistant
        if not _has_assistant_skill(agent_cfg):
            _print_assistant_required(console, name)
            sys.exit(1)
        _launch_gateway(agent_name=name, console=console)
    else:
        # Mode local : REPL classique dans le CWD
        from marius.host.repl import run_repl
        from marius.storage.memory_store import MemoryStore
        from marius.gateway.workspace import ensure_workspace, memory_db_path
        ensure_workspace(name)
        memory_store = MemoryStore(memory_db_path(name))
        run_repl(
            entry,
            agent_config=agent_cfg,
            permission_mode=config.permission_mode,
            memory_store=memory_store,
        )


def _cmd_telegram(args) -> None:
    from rich.console import Console
    console = Console(highlight=False)
    tg_cmd = getattr(args, "tg_cmd", None)

    if tg_cmd == "setup" or tg_cmd is None:
        from marius.channels.telegram.setup import run_telegram_setup
        run_telegram_setup(console)
        return

    if tg_cmd == "status":
        from marius.channels.telegram.config import is_configured, load as load_tg
        from marius.channels.telegram.api import get_me
        from rich.table import Table

        cfg = load_tg()
        console.print()
        if not cfg:
            console.print("[dim]Telegram non configuré. Lancez marius telegram setup.[/]\n")
            return

        me = get_me(cfg.token) if cfg.token else None
        bot_label   = f"@{me['username']}" if me else "[dim]inaccessible[/]"
        users_label = ", ".join(str(u) for u in cfg.allowed_users) or "tous"
        enabled_label = "[green]activé[/]" if cfg.enabled else "[dim]désactivé[/]"

        t = Table.grid(padding=(0, 2))
        t.add_column(style="dim", no_wrap=True)
        t.add_column()
        t.add_row("bot",     bot_label)
        t.add_row("agent",   cfg.agent_name)
        t.add_row("users",   users_label)
        t.add_row("statut",  enabled_label)
        console.print("[bold color(208)]Canal Telegram[/]\n")
        console.print(t)
        console.print()
        return

    console.print("[dim]Usage : marius telegram [setup|status][/]\n")


def _cmd_config_show(agent_name: str | None = None) -> None:
    """Affiche la configuration courante d'un agent sans éditer."""
    from rich.console import Console
    from rich.table import Table

    from marius.config.contracts import ALL_TOOLS
    from marius.config.store import ConfigStore
    from marius.kernel.posture import ASSISTANT_SKILL
    from marius.provider_config.store import ProviderStore

    console = Console(highlight=False)
    config_store = ConfigStore()
    config = config_store.load()
    if config is None:
        console.print("\n[dim]Aucune configuration. Lancez[/] marius setup[dim].[/]\n")
        return

    provider_store = ProviderStore()
    providers = {p.id: p for p in provider_store.load()}

    name = agent_name or config.main_agent
    agent_cfg = config.get_agent(name)
    if agent_cfg is None:
        console.print(f"\n[bold color(208)]Agent inconnu :[/] {name}\n")
        return

    provider = providers.get(agent_cfg.provider_id)
    provider_label = f"{provider.name}  [dim]{provider.model}[/]" if provider else f"[dim]{agent_cfg.provider_id}[/]"
    is_main = name == config.main_agent
    star = "  [color(208)]★ agent principal[/]" if is_main else ""

    console.print()
    console.print(f"[bold color(208)]Agent :[/] {name}{star}\n")

    # Provider + scheduler
    meta = Table.grid(padding=(0, 2))
    meta.add_column(style="dim", no_wrap=True)
    meta.add_column()
    meta.add_row("provider",    provider_label)
    meta.add_row("modèle",      agent_cfg.model)
    meta.add_row("permissions", config.permission_mode)
    if getattr(agent_cfg, "scheduler_enabled", False):
        meta.add_row("dreaming",  getattr(agent_cfg, "dream_time", "—"))
        meta.add_row("daily",     getattr(agent_cfg, "daily_time", "—"))
    console.print(meta)

    # Skills
    active_skills = set(agent_cfg.skills or [])
    console.print(f"\n[bold]Skills[/]  [dim]({len(active_skills)} actif(s))[/]\n")
    from marius.kernel.skills import SkillReader
    available = {m.name: m for m in SkillReader().list()}
    skill_t = Table.grid(padding=(0, 2))
    skill_t.add_column(no_wrap=True)
    skill_t.add_column(style="dim")
    skill_t.add_column(style="dim")
    for s in agent_cfg.skills:
        meta_s = available.get(s)
        desc = meta_s.description if meta_s else ""
        gw_note = "  [color(208)]→ gateway[/]" if s == ASSISTANT_SKILL else ""
        skill_t.add_row(f"[green]✓[/] {s}", desc, gw_note)
    for s in sorted(available):
        if s not in active_skills:
            meta_s = available[s]
            skill_t.add_row(f"[dim]○ {s}[/]", meta_s.description, "")
    console.print(skill_t)

    # Tools
    active_tools = set(agent_cfg.tools or [])
    console.print(f"\n[bold]Tools[/]  [dim]({len(active_tools)} actif(s))[/]\n")
    tool_t = Table.grid(padding=(0, 2))
    tool_t.add_column(no_wrap=True)
    for tool in ALL_TOOLS:
        if tool in active_tools:
            tool_t.add_row(f"[green]✓[/] {tool}")
        else:
            tool_t.add_row(f"[dim]○ {tool}[/]")
    console.print(tool_t)

    console.print(
        f"\n[dim]  marius config tool +<nom> / -<nom>  pour activer/désactiver un tool[/]"
        f"\n[dim]  marius skills activate <nom>         pour activer un skill[/]\n"
    )


def _cmd_config_tool(change: str, agent_name: str | None = None) -> None:
    """Active ou désactive un tool pour un agent : +nom ou -nom."""
    from rich.console import Console
    from marius.config.contracts import ALL_TOOLS
    from marius.config.store import ConfigStore
    from dataclasses import replace

    console = Console(highlight=False)
    change = change.strip()
    if not change or change[0] not in ("+", "-"):
        console.print("\n[dim]Usage : marius config tool +<nom> ou -<nom>[/]\n")
        return

    action  = change[0]
    tool_name = change[1:].strip()
    if not tool_name:
        console.print("\n[dim]Nom de tool manquant.[/]\n")
        return
    if tool_name not in ALL_TOOLS:
        console.print(
            f"\n[bold color(208)]Tool inconnu :[/] {tool_name}\n"
            f"  Tools disponibles : {', '.join(ALL_TOOLS)}\n"
        )
        return

    config_store = ConfigStore()
    config = config_store.load()
    if config is None:
        console.print("\n[dim]Aucune configuration. Lancez[/] marius setup[dim].[/]\n")
        return

    name = agent_name or config.main_agent
    agent_cfg = config.get_agent(name)
    if agent_cfg is None:
        console.print(f"\n[bold color(208)]Agent inconnu :[/] {name}\n")
        return

    tools = list(agent_cfg.tools or [])
    if action == "+":
        if tool_name in tools:
            console.print(f"\n[dim]Tool '{tool_name}' déjà actif pour {name}.[/]\n")
            return
        tools.append(tool_name)
        verb = "activé"
    else:
        if tool_name not in tools:
            console.print(f"\n[dim]Tool '{tool_name}' n'est pas actif pour {name}.[/]\n")
            return
        tools.remove(tool_name)
        verb = "désactivé"

    # Préserver l'ordre de ALL_TOOLS
    ordered = [t for t in ALL_TOOLS if t in set(tools)]
    updated = replace(agent_cfg, tools=ordered)
    config.agents[name] = updated
    config_store.save(config)
    console.print(f"\n[dim]Tool '{tool_name}' {verb} pour l'agent '{name}'.[/]\n")


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
        agent_cfg = config.get_agent(name) if config else None
        if not _has_assistant_skill(agent_cfg):
            _print_assistant_required(console, name)
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
        from marius.gateway.service import (
            agent_active_state, agent_enabled_state, is_service_installed, is_systemd_available,
        )
        from rich.table import Table
        console.print()
        t = Table.grid(padding=(0, 2))
        t.add_column(style="bold", no_wrap=True)
        t.add_column()   # process
        t.add_column()   # systemd actif
        t.add_column(style="dim")  # systemd enabled
        use_systemd = is_systemd_available() and is_service_installed()
        for agent_name in config.agents:
            proc_label = "[green]actif[/]" if is_running(agent_name) else "[dim]inactif[/]"
            if use_systemd:
                sd_state   = agent_active_state(agent_name)
                sd_enabled = agent_enabled_state(agent_name)
                sd_label   = f"[green]{sd_state}[/]" if sd_state == "active" else f"[dim]{sd_state}[/]"
                t.add_row(agent_name, proc_label, sd_label, sd_enabled)
            else:
                t.add_row(agent_name, proc_label)
        console.print("[bold color(208)]État des gateways[/]\n")
        console.print(t)
        if use_systemd:
            console.print("\n  [dim]service systemd installé[/]")
        else:
            console.print("\n  [dim]service systemd non installé — lancez marius gateway install-service[/]")
        console.print()
        return

    if gw_cmd == "install-service":
        from marius.gateway.service import install_service, is_systemd_available, linger_hint
        if not is_systemd_available():
            console.print("\n[bold color(208)]systemd non disponible sur ce système.[/]\n")
            return
        path = install_service()
        console.print(f"\n[dim]Service installé : {path}[/]")
        hint = linger_hint()
        if hint:
            console.print(
                f"\n  [bold color(208)]Pour démarrer sans session ouverte :[/]\n"
                f"    {hint}\n"
            )
        console.print(
            "\n  Activez un agent avec :\n"
            "    [bold]marius gateway enable --agent main[/]\n"
        )
        return

    if gw_cmd == "uninstall-service":
        from marius.gateway.service import is_service_installed, uninstall_service
        if not is_service_installed():
            console.print("\n[dim]Service non installé.[/]\n")
            return
        uninstall_service()
        console.print("\n[dim]Service systemd supprimé.[/]\n")
        return

    if gw_cmd == "enable":
        name = _resolve_agent_name()
        if not name:
            console.print("\n[dim]Aucun agent configuré.[/]\n")
            return
        agent_cfg = config.get_agent(name) if config else None
        if not _has_assistant_skill(agent_cfg):
            _print_assistant_required(console, name)
            return
        from marius.gateway.service import enable_agent, is_service_installed, is_systemd_available
        if not is_systemd_available():
            console.print("\n[bold color(208)]systemd non disponible.[/]\n")
            return
        if not is_service_installed():
            console.print(
                "\n[bold color(208)]Service non installé.[/]\n"
                "  Lancez d'abord : [bold]marius gateway install-service[/]\n"
            )
            return
        ok, err = enable_agent(name)
        if ok:
            console.print(f"\n[dim]Gateway '{name}' activé (démarrera au login).[/]\n")
        else:
            console.print(f"\n[bold color(208)]Échec :[/] {err}\n")
        return

    if gw_cmd == "disable":
        name = _resolve_agent_name()
        if not name:
            console.print("\n[dim]Aucun agent configuré.[/]\n")
            return
        from marius.gateway.service import disable_agent, is_systemd_available
        if not is_systemd_available():
            console.print("\n[bold color(208)]systemd non disponible.[/]\n")
            return
        ok, err = disable_agent(name)
        if ok:
            console.print(f"\n[dim]Gateway '{name}' désactivé.[/]\n")
        else:
            console.print(f"\n[bold color(208)]Échec :[/] {err}\n")
        return

    console.print("[dim]Usage : marius gateway [start|stop|status|install-service|uninstall-service|enable|disable][/]\n")


def _cmd_logs(args) -> None:
    """Affiche le journal local de diagnostic."""
    from rich.console import Console
    from rich.table import Table

    from marius.storage.log_store import clear_logs, log_path, read_logs

    console = Console(highlight=False)
    path = log_path()

    if getattr(args, "path", False):
        console.print(str(path))
        return

    if getattr(args, "clear", False):
        clear_logs()
        console.print(f"\n[dim]Logs vidés : {path}[/]\n")
        return

    entries = read_logs(limit=max(0, int(getattr(args, "tail", 80) or 80)))
    console.print()
    console.print("[bold color(208)]Logs Marius[/]")
    console.print(f"[dim]{path}[/]\n")
    if not entries:
        console.print("  [dim]Aucune entrée.[/]\n")
        return

    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", no_wrap=True)
    table.add_column(style="bold", no_wrap=True)
    table.add_column()
    for entry in entries:
        table.add_row(_short_time(entry.timestamp), entry.event, _format_log_data(entry.data))
    console.print(table)
    console.print()


def _short_time(timestamp: str) -> str:
    # ISO UTC : 2026-05-09T12:34:56.123+00:00 → 12:34:56
    if "T" in timestamp:
        return timestamp.split("T", 1)[1].split(".", 1)[0].split("+", 1)[0]
    return timestamp


def _format_log_data(data: dict) -> str:
    preferred = [
        "cwd",
        "project",
        "provider",
        "provider_kind",
        "model",
        "permission_mode",
        "user_preview",
        "assistant_preview",
        "tool",
        "target",
        "ok",
        "error",
        "retryable",
        "tool_results",
        "input_tokens",
        "estimated_input_tokens",
    ]
    parts = []
    for key in preferred:
        if key not in data or data[key] in ("", None):
            continue
        value = str(data[key])
        if len(value) > 160:
            value = value[:159] + "…"
        parts.append(f"{key}={value}")
    return "  ".join(parts)


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


# ── helpers assistant skill ───────────────────────────────────────────────────


def _cmd_web(args) -> None:
    """Proxy HTTP ↔ socket gateway. Lance le gateway si nécessaire, puis sert en foreground."""
    from rich.console import Console
    from marius.config.store import ConfigStore
    from marius.gateway.launcher import is_running, start
    from marius.gateway.workspace import socket_path
    from marius.channels.web.server import WebServer

    console = Console(highlight=False)
    config = ConfigStore().load()
    name = getattr(args, "agent", None) or (config.main_agent if config else None)
    port = getattr(args, "port", 8765)

    if not name:
        console.print("\n[dim]Aucun agent configuré. Lancez marius setup.[/]\n")
        return

    if not is_running(name):
        console.print(f"\n[dim]Démarrage du gateway '{name}'…[/]")
        ok = start(name)
        if not ok:
            console.print(f"\n[bold color(208)]Impossible de démarrer le gateway '{name}'.[/]\n")
            return

    server = WebServer(agent_name=name, socket_path=socket_path(name), port=port)
    try:
        server.connect()
    except OSError as exc:
        console.print(f"\n[bold color(208)]Connexion au gateway impossible : {exc}[/]\n")
        return

    console.print(f"\n[green]✓[/] Interface web sur [bold]http://localhost:{port}[/]")
    console.print("[dim]Ctrl+C pour arrêter le web (le gateway continue).[/]\n")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.shutdown()


def _has_assistant_skill(agent_cfg) -> bool:
    """Vérifie que le skill assistant est activé pour cet agent."""
    from marius.kernel.posture import ASSISTANT_SKILL
    if agent_cfg is None:
        return False
    return ASSISTANT_SKILL in set(agent_cfg.skills or [])


def _print_assistant_required(console, agent_name: str) -> None:
    """Affiche le message d'erreur quand le skill assistant est requis."""
    console.print(
        f"\n[bold color(208)]Le gateway nécessite le skill assistant.[/]\n"
        f"  Activez-le avec :\n"
        f"    [bold]marius skills activate assistant --agent {agent_name}[/]\n"
    )

