"""REPL interactif de Marius."""

from __future__ import annotations

import random
import threading
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.status import Status
from rich.table import Table
from rich.text import Text
from rich.theme import Theme

from marius.adapters.context_window import make_api_resolver
from marius.adapters.http_provider import make_adapter
from marius.kernel.compaction import CompactionConfig, CompactionLevel, compaction_level, resolve_token_count
from marius.kernel.context_factory import build_system_prompt
from marius.kernel.context_window import FALLBACK_CONTEXT_WINDOW, resolve_context_window
from marius.kernel.contracts import Message, Role, ToolCall, ToolResult
from marius.kernel.skills import SkillCommand, SkillReader, collect_skill_commands
from marius.kernel.memory_context import format_memory_block
from marius.kernel.permission_guard import PermissionGuard
from marius.kernel.posture import maybe_activate_dev_posture, uses_dev_posture
from marius.kernel.provider import ProviderError
from marius.kernel.runtime import RuntimeOrchestrator, TurnInput
from marius.kernel.session import SessionRuntime
from marius.kernel.session_observations import format_session_observations, observe_tool_result
from marius.kernel.tool_router import ToolRouter
from marius.provider_config.contracts import ProviderEntry
from marius.provider_config.registry import PROVIDER_REGISTRY
from marius.provider_config.store import ProviderStore
from marius.provider_config.wizard import run_add_provider, run_set_model
from marius.render.adapter import RenderSurface, render_turn_output
from marius.storage.memory_store import MemoryStore
from marius.storage.approval_store import ApprovalStore
from marius.storage.log_store import log_event, preview
from marius.storage.project_store import ProjectStore
from marius.storage.session_corpus import SessionRecord, build_transcript, write_session_file
from marius.storage.ui_history import InMemoryVisibleHistoryStore, VisibleHistoryEntry
from marius.tools.factory import build_tool_entries
from marius.tools.spawn_agent import make_spawn_agent_tool


_THEME = Theme({
    "prompt":         "bold white",
    "dim":            "dim",
    "tool.bullet":    "bold dim",
    "tool.verb":      "bold",
    "tool.target":    "dim",
    "tool.ok":        "dim green",
    "tool.err":       "dim red",
    "error":          "bold red",
    "info.key":       "dim",
    "info.val":       "white",
    "cmd.name":       "bold color(208)",
    "cmd.desc":       "dim",
})

_console = Console(theme=_THEME, highlight=False)

_MARIUS_ASCII = """\
[#E8761A]███╗   ███╗  █████╗  ██████╗ ██╗██╗   ██╗███████╗[/]
[#E0701A]████╗ ████║ ██╔══██╗ ██╔══██╗██║██║   ██║██╔════╝[/]
[#D86818]██╔████╔██║ ███████║ ██████╔╝██║██║   ██║███████╗[/]
[#C05010]██║╚██╔╝██║ ██╔══██║ ██╔══██╗██║██║   ██║╚════██║[/]
[#A03A08]██║ ╚═╝ ██║ ██║  ██║ ██║  ██║██║╚██████╔╝███████║[/]
[#7A2A00]╚═╝     ╚═╝ ╚═╝  ╚═╝ ╚═╝  ╚═╝╚═╝ ╚═════╝╚══════╝[/]"""

_TIPS = [
    ("/model",    "changer de modèle"),
    ("/provider", "ajouter un provider"),
    ("/context",  "état du contexte"),
    ("/new",      "nouvelle conversation"),
    ("/help",     "toutes les commandes"),
    ("/exit",     "quitter"),
]

_SPINNER_WORDS = [
    "Réflexion", "Analyse", "Traitement",
    "Exploration", "Synthèse", "Recherche",
]

_COMMANDS: dict[str, str] = {
    "/model":     "changer le modèle actif",
    "/provider":  "ajouter ou gérer les providers",
    "/context":   "afficher l'état du contexte et du niveau de compaction",
    "/compact":   "forcer la compaction du contexte (trim)",
    "/new":       "démarrer une nouvelle conversation",
    "/verbose":   "activer / désactiver l'affichage détaillé des outils",
    "/remember":  "mémoriser un fait  (/remember <texte>)",
    "/memories":  "lister les souvenirs enregistrés",
    "/forget":    "supprimer un souvenir  (/forget <id>)",
    "/doctor":    "diagnostic de l'installation (provider, SearxNG, gateway…)",
    "/dream":     "consolider la mémoire (dreaming LLM)",
    "/daily":     "générer le briefing du jour",
    "/stop":      "interrompre l'inférence en cours",
    "/help":      "afficher toutes les commandes",
    "/exit":      "quitter Marius",
}

_VERBOSE_SUMMARY_MAX = 300  # caractères affichés en mode verbose

# Seuil d'auto-compaction : déclenche un trim si >= 80% de la fenêtre
_AUTO_COMPACT_THRESHOLD = 0.80


# ── résolution de la fenêtre de contexte ─────────────────────────────────────


def _resolve_window(entry: ProviderEntry) -> int:
    defn = PROVIDER_REGISTRY.get(entry.provider)
    if defn is None:
        return FALLBACK_CONTEXT_WINDOW
    api_resolver = None
    if defn.context_window_api_endpoint:
        api_resolver = make_api_resolver(
            base_url=entry.base_url,
            api_endpoint=defn.context_window_api_endpoint,
            model=entry.model,
            api_key=entry.api_key,
        )
    return resolve_context_window(
        model=entry.model,
        strategy=defn.context_window_strategy,
        api_resolver=api_resolver,
    )


# ── welcome ───────────────────────────────────────────────────────────────────


def _welcome(entry: ProviderEntry, loaded_context: list[str] | None = None) -> None:
    auth_label = entry.auth_type
    provider_label = f"{auth_label} · {entry.model}" if entry.model else auth_label
    context_label = " · ".join(loaded_context) if loaded_context else "(aucun)"

    info = Table.grid(padding=(0, 1))
    info.add_column(style="info.key", no_wrap=True)
    info.add_column(style="info.val", no_wrap=True)
    info.add_row("provider", provider_label)
    info.add_row("profil",   "local")
    info.add_row("projet",   Path.cwd().name)
    info.add_row("session",  "default")
    info.add_row("contexte", context_label)

    tips = Table.grid(padding=(0, 2))
    tips.add_column(style="cmd.name", no_wrap=True)
    tips.add_column(style="cmd.desc")
    for name, desc in _TIPS:
        tips.add_row(name, desc)

    right_body = Table.grid()
    right_body.add_row(Text("Pour démarrer", style="bold color(208)"))
    right_body.add_row(Text(""))
    right_body.add_row(tips)
    right_body.add_row(Text(""))
    right_body.add_row(Text("Activité récente", style="bold color(208)"))
    right_body.add_row(Text(""))
    right_body.add_row(Text("  Aucune activité récente", style="dim"))

    bottom = Table.grid(expand=True, padding=(0, 3))
    bottom.add_column(ratio=4)
    bottom.add_column(ratio=6)
    bottom.add_row(info, right_body)

    logo = Text.from_markup(_MARIUS_ASCII)
    logo.no_wrap = True

    body = Table.grid(padding=(0, 0))
    body.add_row(logo)
    body.add_row(Text(""))
    body.add_row(bottom)

    _console.print()
    _console.print(Panel(body, border_style="dim", padding=(1, 2)))
    _console.print("[dim]  ? pour les raccourcis  ·  /exit ou Ctrl-D pour quitter[/]\n")


# ── commandes ─────────────────────────────────────────────────────────────────


def _cmd_help(skill_commands: dict[str, SkillCommand] | None = None) -> None:
    _console.print()
    _console.print("[bold color(208)]Commandes disponibles[/]\n")
    t = Table.grid(padding=(0, 2))
    t.add_column(style="cmd.name", no_wrap=True)
    t.add_column(style="cmd.desc")
    for name, desc in _COMMANDS.items():
        t.add_row(name, desc)
    if skill_commands:
        _console.print(t)
        _console.print()
        _console.print("[bold color(208)]Commandes skills[/]\n")
        t = Table.grid(padding=(0, 2))
        t.add_column(style="cmd.name", no_wrap=True)
        t.add_column(style="cmd.desc")
        t.add_column(style="dim")
        for sc in skill_commands.values():
            t.add_row(f"/{sc.name}", sc.description, f"[{sc.skill_name}]")
    _console.print(t)
    _console.print()


def _cmd_context(session: SessionRuntime, entry: ProviderEntry) -> None:
    messages = session.internal_messages(include_summary=True, include_tool_results=True)
    turns = len(session.state.turns)
    window = _resolve_window(entry)
    from marius.kernel.compaction import estimate_tokens_from_messages
    estimated = estimate_tokens_from_messages(messages)
    last_provider = session.state.turns[-1].metadata.get("provider_input_tokens") if turns else None
    tokens = last_provider if last_provider is not None else estimated
    ratio = tokens / window if window > 0 else 0
    pct = ratio * 100

    config = CompactionConfig(context_window_tokens=window)
    level = compaction_level(tokens, config)

    _level_colors = {
        CompactionLevel.NONE:      "green",
        CompactionLevel.TRIM:      "yellow",
        CompactionLevel.SUMMARIZE: "dark_orange",
        CompactionLevel.RESET:     "bold red",
    }
    color = _level_colors.get(level, "white")
    source = "provider" if last_provider is not None else "estimé"

    _console.print()
    _console.print("[bold color(208)]Contexte[/]\n")
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", no_wrap=True)
    t.add_column(no_wrap=True)
    t.add_row("tokens",   f"[{color}]{tokens:,}[/] / {window:,}  ({pct:.1f}%)  [{source}]")
    t.add_row("tours",    str(turns))
    t.add_row("messages", str(len(messages)))
    t.add_row("niveau",   f"[{color}]{level.value}[/]")
    _console.print(t)
    _console.print()


def _cmd_compact(
    session: SessionRuntime,
    orchestrator: RuntimeOrchestrator,
    entry: ProviderEntry,
) -> None:
    kept = orchestrator.compaction_config.keep_recent_turns
    before = len(session.state.turns)
    _do_trim(session, keep_recent=kept)
    after = len(session.state.turns)
    removed = before - after
    _console.print(
        f"\n  [dim]Compaction effectuée — "
        f"{removed} tour(s) supprimé(s), {after} conservé(s).[/]\n"
    )


def _cmd_new(session: SessionRuntime) -> SessionRuntime:
    session.state.turns.clear()
    session.state.compaction_notices.clear()
    session.state.derived_context_summary = ""
    session.state.derived_context_summary_message = None
    _console.print("\n  [dim]Nouvelle conversation démarrée.[/]\n")
    return session


def _cmd_remember(text: str, memory_store: MemoryStore) -> None:
    text = text.strip()
    if not text:
        _console.print("  [dim]Usage : /remember <texte>[/]\n")
        return
    memory_id = memory_store.add(text)
    _console.print(f"\n  [dim]Souvenir #{memory_id} enregistré.[/]\n")


def _cmd_memories(memory_store: MemoryStore) -> None:
    entries = memory_store.list(limit=30)
    _console.print()
    if not entries:
        _console.print("  [dim]Aucun souvenir enregistré.[/]\n")
        return
    _console.print("[bold color(208)]Souvenirs[/]\n")
    t = Table.grid(padding=(0, 2))
    t.add_column(style="dim", no_wrap=True)
    t.add_column()
    t.add_column(style="dim")
    for e in entries:
        tag = f"[{e.tags}]" if e.tags else ""
        t.add_row(f"#{e.id}", e.content, tag)
    _console.print(t)
    _console.print()


def _cmd_forget(raw_id: str, memory_store: MemoryStore) -> None:
    raw_id = raw_id.strip()
    if not raw_id.lstrip("#").isdigit():
        _console.print("  [dim]Usage : /forget <id>[/]\n")
        return
    memory_id = int(raw_id.lstrip("#"))
    if memory_store.remove(memory_id):
        _console.print(f"\n  [dim]Souvenir #{memory_id} supprimé.[/]\n")
    else:
        _console.print(f"\n  [dim]Souvenir #{memory_id} introuvable.[/]\n")


# ── dreaming / daily ─────────────────────────────────────────────────────────


def _cmd_dream(
    memory_store: MemoryStore,
    entry: ProviderEntry,
    active_skills: list[str] | None,
    cwd: Path,
) -> None:
    from marius.dreaming.engine import run_dreaming

    _console.print("\n  [dim]Dreaming en cours…[/]")
    with Status("[dim]Consolidation mémorielle…[/]", spinner="dots", spinner_style="color(208)", console=_console):
        result = run_dreaming(
            memory_store=memory_store,
            entry=entry,
            active_skills=active_skills,
            project_root=cwd,
        )
    _console.print(f"\n  [dim]{result}[/]\n")


def _cmd_daily(
    memory_store: MemoryStore,
    entry: ProviderEntry,
    active_skills: list[str] | None,
    cwd: Path,
    agent_name: str | None = None,
) -> None:
    # Vérifie d'abord le cache généré par le scheduler du gateway (< 12h)
    briefing = _read_daily_cache(agent_name)
    if briefing:
        _console.print("\n  [dim]Briefing du scheduler (cache)[/]")
    else:
        from marius.dreaming.engine import run_daily
        with Status("[dim]Génération du briefing…[/]", spinner="dots", spinner_style="color(208)", console=_console):
            briefing = run_daily(
                memory_store=memory_store,
                entry=entry,
                active_skills=active_skills,
                project_root=cwd,
            )
    _console.print()
    _console.print(Markdown(briefing))
    _console.print()


def _read_daily_cache(agent_name: str | None, max_age_hours: float = 12.0) -> str | None:
    """Retourne le briefing mis en cache par le scheduler si récent."""
    if not agent_name:
        return None
    try:
        from marius.gateway.workspace import daily_cache_path
        import os
        cache = daily_cache_path(agent_name)
        if not cache.exists():
            return None
        age_hours = (Path(os.devnull).stat().st_mtime - cache.stat().st_mtime) / 3600
        # Utilise l'heure de modification du fichier
        import time as _time
        age_hours = (_time.time() - cache.stat().st_mtime) / 3600
        if age_hours > max_age_hours:
            return None
        return cache.read_text(encoding="utf-8")
    except (OSError, ImportError):
        return None


# ── compaction ────────────────────────────────────────────────────────────────


def _do_trim(session: SessionRuntime, *, keep_recent: int = 10) -> None:
    """Supprime les tours les plus anciens en conservant les `keep_recent` derniers."""
    if len(session.state.turns) > keep_recent:
        session.state.turns = session.state.turns[-keep_recent:]


def _maybe_auto_compact(
    session: SessionRuntime,
    orchestrator: RuntimeOrchestrator,
    entry: ProviderEntry,
    tokens: int,
) -> None:
    window = _resolve_window(entry)
    if window <= 0:
        return
    ratio = tokens / window
    if ratio >= _AUTO_COMPACT_THRESHOLD:
        kept = orchestrator.compaction_config.keep_recent_turns
        _do_trim(session, keep_recent=kept)
        _console.print(
            f"  [dim]Auto-compaction ({ratio*100:.0f}% de la fenêtre) — "
            f"contexte réduit aux {kept} derniers tours.[/]\n"
        )


# ── dispatch ──────────────────────────────────────────────────────────────────


def _dispatch_command(
    message: str,
    store: ProviderStore,
    session: SessionRuntime,
    orchestrator: RuntimeOrchestrator,
    entry: ProviderEntry,
    memory_store: MemoryStore,
    stop_event: threading.Event | None = None,
    skill_commands: dict[str, SkillCommand] | None = None,
) -> tuple[bool, SessionRuntime, str | None]:
    """Gère les commandes slash.

    Retourne (continuer, session, turn_message).
    turn_message est non-None si la commande doit déclencher un tour LLM.
    """
    parts = message.split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd == "/exit":
        return False, session, None

    if cmd == "/stop":
        if stop_event is not None:
            stop_event.set()
            _console.print("\n  [dim]Inférence interrompue.[/]\n")
        else:
            _console.print("\n  [dim]Aucune inférence en cours.[/]\n")
        return True, session, None

    if cmd == "/help":
        _cmd_help(skill_commands)
        return True, session, None

    if cmd == "/model":
        run_set_model(store=store, console=_console)
        return True, session, None

    if cmd == "/provider":
        run_add_provider(store=store, console=_console)
        return True, session, None

    if cmd == "/context":
        _cmd_context(session, entry)
        return True, session, None

    if cmd == "/compact":
        _cmd_compact(session, orchestrator, entry)
        return True, session, None

    if cmd == "/new":
        session = _cmd_new(session)
        return True, session, None

    if cmd == "/remember":
        _cmd_remember(arg, memory_store)
        return True, session, None

    if cmd == "/memories":
        _cmd_memories(memory_store)
        return True, session, None

    if cmd == "/forget":
        _cmd_forget(arg, memory_store)
        return True, session, None

    if cmd == "/doctor":
        from marius.config.doctor import print_report, run_doctor
        sections = run_doctor()
        print_report(sections)
        return True, session, None

    # Commandes dynamiques issues des skills
    cmd_name = cmd.lstrip("/")
    if skill_commands and cmd_name in skill_commands:
        skill_cmd = skill_commands[cmd_name]
        if not skill_cmd.prompt and not arg:
            _console.print(f"  [dim]Usage : {cmd} <description>[/]\n")
            return True, session, None
        turn_msg = f"{skill_cmd.prompt}\n\n{arg}".strip() if skill_cmd.prompt else arg
        return True, session, turn_msg

    _console.print(f"[dim]Commande inconnue : {cmd}. Tapez /help pour la liste.[/]\n")
    return True, session, None


# ── boucle principale ─────────────────────────────────────────────────────────


def _make_ask_callback():
    """Retourne un callback interactif pour les décisions de permission."""
    def on_ask(tool_name: str, arguments: dict, reason: str) -> bool:
        _console.print(f"\n  [bold color(208)]Permission requise[/]  [dim]{tool_name}[/]")
        _console.print(f"  [dim]{reason}[/]")
        try:
            raw = _console.input("  Autoriser ? [[dim]o/N[/]]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raw = "n"
        approved = raw in ("o", "oui", "y", "yes")
        if not approved:
            _console.print("  [dim]Refusé.[/]\n")
        return approved
    return on_ask


def _make_approval_recorder(store: ApprovalStore):
    def recorder(event: dict[str, Any]) -> None:
        store.record(
            fingerprint=str(event.get("fingerprint") or ""),
            tool_name=str(event.get("tool_name") or ""),
            arguments=dict(event.get("arguments") or {}),
            reason=str(event.get("reason") or ""),
            mode=str(event.get("mode") or ""),
            cwd=str(event.get("cwd") or ""),
            approved=bool(event.get("approved", False)),
        )
    return recorder


def _build_tool_router(
    enabled_tools: list[str] | None,
    memory_store: MemoryStore,
    cwd: Path,
    *,
    guard: "Any | None" = None,
    entry: "Any | None" = None,
    active_skills: list[str] | None = None,
    agent_name: str | None = None,
    permission_mode: str = "limited",
) -> ToolRouter:
    """Construit le router depuis la liste des tools actifs de l'agent.

    spawn_agent est construit en deux passes : d'abord les entries de base,
    puis spawn_agent y est ajouté avec cette liste comme contexte workers.
    """
    base_entries = build_tool_entries(
        enabled_tools,
        memory_store,
        cwd,
        entry=entry,
        active_skills=active_skills,
        agent_name=agent_name,
    )

    if entry is not None and (enabled_tools is None or "spawn_agent" in enabled_tools):
        spawn_tool = make_spawn_agent_tool(
            entry,
            base_entries,
            permission_mode=permission_mode,
            cwd=cwd,
        )
        base_entries = [*base_entries, spawn_tool]

    return ToolRouter(base_entries, guard=guard)


# ── verbes d'affichage pour les outils ───────────────────────────────────────

_TOOL_VERBS: dict[str, str] = {
    "read_file":   "Lecture",
    "list_dir":    "Exploration",
    "write_file":  "Écriture",
    "make_dir":    "Dossier",
    "move_path":   "Déplacement",
    "explore_tree": "Exploration",
    "explore_grep": "Recherche",
    "explore_summary": "Synthèse",
    "run_bash":    "Exécution",
    "web_fetch":   "Fetch",
    "web_search":  "Recherche web",
    "vision":      "Vision",
    "skill_view":  "Skill",
    "skill_create": "Skill",
    "skill_list":  "Skills",
    "skill_reload": "Skills",
    "host_agent_list": "Agents",
    "host_agent_save": "Agent",
    "host_agent_delete": "Agent",
    "host_telegram_configure": "Telegram",
    "host_status": "Status",
    "host_doctor": "Doctor",
    "host_logs":   "Logs",
    "host_gateway_restart": "Gateway",
    "project_list": "Projets",
    "project_set_active": "Projet",
    "approval_list": "Approvals",
    "approval_decide": "Approval",
    "approval_forget": "Approval",
    "secret_ref_list": "Secrets",
    "secret_ref_save": "Secret",
    "secret_ref_delete": "Secret",
    "secret_ref_prepare_file": "Secret",
    "provider_list": "Providers",
    "provider_save": "Provider",
    "provider_delete": "Provider",
    "provider_models": "Models",
    "dreaming_run": "Dreaming",
    "daily_digest": "Daily",
    "self_update_propose": "Update",
    "self_update_report_bug": "Bug",
    "self_update_list": "Updates",
    "self_update_show": "Update",
    "self_update_apply": "Update",
    "self_update_rollback": "Rollback",
    "watch_add": "Veille",
    "watch_list": "Veille",
    "watch_remove": "Veille",
    "watch_run": "Veille",
    "rag_source_add": "RAG",
    "rag_source_list": "RAG",
    "rag_source_sync": "RAG",
    "rag_search": "RAG",
    "rag_get": "RAG",
    "rag_promote_to_memory": "RAG",
    "rag_checklist_add": "Liste",
    "caldav_doctor": "Calendar",
    "caldav_agenda": "Calendar",
    "caldav_maintenance": "Calendar",
    "sentinelle_scan": "Sentinelle",
    "spawn_agent": "Workers",
}

_TOOL_TARGET_KEYS: dict[str, str] = {
    "read_file":  "path",
    "list_dir":   "path",
    "write_file": "path",
    "make_dir":   "path",
    "move_path":  "destination",
    "explore_tree": "path",
    "explore_grep": "pattern",
    "explore_summary": "path",
    "run_bash":   "command",
    "web_fetch":  "url",
    "web_search": "query",
    "vision":     "path",
    "skill_view": "name",
    "skill_create": "name",
    "host_agent_list": "agent",
    "host_agent_save": "name",
    "host_agent_delete": "name",
    "host_telegram_configure": "agent",
    "host_status": "agent",
    "host_doctor": "agent",
    "host_logs": "event",
    "host_gateway_restart": "agent",
    "project_list": "limit",
    "project_set_active": "path",
    "approval_list": "limit",
    "approval_decide": "id",
    "approval_forget": "id",
    "secret_ref_list": "name",
    "secret_ref_save": "name",
    "secret_ref_delete": "name",
    "secret_ref_prepare_file": "name",
    "provider_list": "name",
    "provider_save": "name",
    "provider_delete": "id",
    "provider_models": "name",
    "dreaming_run": "archive_sessions",
    "daily_digest": "project_root",
    "self_update_propose": "title",
    "self_update_report_bug": "title",
    "self_update_list": "kind",
    "self_update_show": "id",
    "self_update_apply": "id",
    "self_update_rollback": "id",
    "watch_add": "title",
    "watch_list": "include_disabled",
    "watch_remove": "id",
    "watch_run": "id",
    "rag_source_add": "name",
    "rag_source_sync": "source_id",
    "rag_search": "query",
    "rag_get": "chunk_id",
    "rag_promote_to_memory": "chunk_id",
    "rag_checklist_add": "list_name",
    "caldav_agenda": "days",
    "caldav_maintenance": "operation",
}


def _tool_verb(call: ToolCall) -> str:
    return _TOOL_VERBS.get(call.name, call.name)


def _tool_target(call: ToolCall) -> str:
    key = _TOOL_TARGET_KEYS.get(call.name, "")
    return str(call.arguments.get(key, "")) if key else ""


def _ensure_search_backend(enabled_tools: list[str] | None) -> None:
    if enabled_tools is not None and "web_search" not in enabled_tools:
        return
    from marius.services.searxng import ensure_searxng_started
    result = ensure_searxng_started()
    log_event("searxng_startup", {
        "agent": "repl",
        "ok": result.ok,
        "status": result.status,
        "url": result.url,
        "compose_file": result.compose_file,
        "detail": result.detail,
    })


def run_repl(
    entry: ProviderEntry,
    store: ProviderStore | None = None,
    *,
    history: InMemoryVisibleHistoryStore | None = None,
    memory_store: MemoryStore | None = None,
    project_store: ProjectStore | None = None,
    agent_config: "Any | None" = None,
    permission_mode: str = "limited",
    verbose: bool = False,
) -> None:
    from datetime import datetime, timezone

    store = store or ProviderStore()
    memory_store = memory_store if memory_store is not None else MemoryStore()
    project_store = project_store if project_store is not None else ProjectStore()
    approval_store = ApprovalStore()
    cwd = Path.cwd()
    window = _resolve_window(entry)
    adapter = make_adapter(entry)
    enabled_tools = agent_config.tools if agent_config is not None else None
    active_skills = list(agent_config.skills) if agent_config is not None else None
    _ensure_search_backend(enabled_tools)
    guard = PermissionGuard(
        mode=permission_mode,
        cwd=cwd,
        on_ask=_make_ask_callback(),
        approval_lookup=approval_store.lookup,
        approval_recorder=_make_approval_recorder(approval_store),
    )
    tool_router = _build_tool_router(
        enabled_tools, memory_store, cwd,
        guard=guard,
        entry=entry,
        active_skills=active_skills,
        agent_name=agent_config.name if agent_config is not None else None,
        permission_mode=permission_mode,
    )
    history = history if history is not None else InMemoryVisibleHistoryStore()
    session_id = "default"
    state = {"verbose": verbose}
    log_event("repl_start", {
        "session_id": session_id,
        "cwd": str(cwd),
        "project": cwd.name,
        "provider": entry.name,
        "provider_kind": entry.provider,
        "model": entry.model,
        "permission_mode": permission_mode,
        "tools": enabled_tools or "all",
    })

    session = SessionRuntime(
        session_id=session_id,
        metadata={"provider": entry.name, "model": entry.model},
    )
    # Snapshot mémoire à l'ouverture — stable pour toute la session
    active_memories = memory_store.get_active_context(cwd)
    memory_block = format_memory_block(active_memories)

    # Commandes REPL déclarées par les skills actifs
    skill_commands: dict[str, SkillCommand] = {}
    if active_skills:
        _reader = SkillReader()
        skill_commands = collect_skill_commands(_reader.load_all(active_skills))

    system_prompt, loaded_context = _build_session_system_prompt(
        cwd,
        active_skills=active_skills,
        memory_block=memory_block,
        session=session,
        agent_name=agent_config.name if agent_config is not None else None,
    )
    orchestrator = RuntimeOrchestrator(
        provider=adapter,
        tool_router=tool_router,
        compaction_config=CompactionConfig(context_window_tokens=window),
    )

    # Enregistre le projet local comme projet actif explicite pour cette session.
    project_store.set_active(cwd)
    opened_at = datetime.now(timezone.utc).isoformat()

    _welcome(entry, loaded_context=loaded_context)

    stop_event: threading.Event | None = None

    try:
        while True:
            try:
                message = _console.input("[prompt]>[/] ").strip()
            except (EOFError, KeyboardInterrupt):
                _console.print()
                break

            if not message:
                continue

            if message.startswith("/"):
                cmd0 = message.split()[0].lower()

                if cmd0 == "/verbose":
                    state["verbose"] = not state["verbose"]
                    label = "activé" if state["verbose"] else "désactivé"
                    _console.print(f"\n  [dim]Mode verbose {label}.[/]\n")
                    continue

                if cmd0 == "/dream":
                    _cmd_dream(memory_store, entry, active_skills, cwd)
                    continue

                if cmd0 == "/daily":
                    _cmd_daily(
                        memory_store, entry, active_skills, cwd,
                        agent_name=agent_config.name if agent_config is not None else None,
                    )
                    continue

                go_on, session, turn_msg = _dispatch_command(
                    message, store, session, orchestrator, entry, memory_store,
                    stop_event=stop_event,
                    skill_commands=skill_commands or None,
                )
                if not go_on:
                    break
                if turn_msg is not None:
                    # Commande skill → déclenche un tour avec le prompt injecté
                    stop_event = threading.Event()
                    system_prompt, _ = _build_session_system_prompt(
                        cwd,
                        active_skills=active_skills,
                        memory_block=memory_block,
                        session=session,
                        agent_name=agent_config.name if agent_config is not None else None,
                    )
                    _run_turn(
                        orchestrator, session, entry, turn_msg,
                        static_system_prompt=system_prompt,
                        active_skills=active_skills,
                        project_root=cwd,
                        tool_router=tool_router,
                        history=history,
                        session_id=session_id,
                        verbose=state["verbose"],
                        memory_store=memory_store,
                        stop_event=stop_event,
                    )
                    stop_event = None
                continue

            stop_event = threading.Event()
            system_prompt, _ = _build_session_system_prompt(
                cwd,
                active_skills=active_skills,
                memory_block=memory_block,
                session=session,
                agent_name=agent_config.name if agent_config is not None else None,
            )
            _run_turn(
                orchestrator, session, entry, message,
                static_system_prompt=system_prompt,
                active_skills=active_skills,
                project_root=cwd,
                tool_router=tool_router,
                history=history,
                session_id=session_id,
                verbose=state["verbose"],
                memory_store=memory_store,
                stop_event=stop_event,
            )
            stop_event = None

    except Exception as exc:
        log_event("repl_unexpected_error", {
            "session_id": session_id,
            "cwd": str(cwd),
            "error": str(exc),
            "error_type": type(exc).__name__,
        })
        _console.print(f"\n[error]Erreur inattendue : {exc}[/]\n")
    finally:
        # Écrit le fichier de corpus session — silencieux, ne bloque jamais
        _write_session_record(session, cwd, opened_at)


def _write_session_record(
    session: SessionRuntime,
    cwd: Path,
    opened_at: str,
) -> None:
    from datetime import datetime, timezone

    try:
        closed_at = datetime.now(timezone.utc).isoformat()
        turns = len(session.state.turns)
        if turns == 0:
            return  # session vide — pas de fichier à écrire
        messages = session.internal_messages(include_summary=True, include_tool_results=False)
        transcript = build_transcript(messages)
        record = SessionRecord(
            project=cwd.name,
            cwd=str(cwd),
            opened_at=opened_at,
            closed_at=closed_at,
            turns=turns,
            transcript=transcript,
        )
        write_session_file(record)
    except Exception:
        pass


def _build_session_system_prompt(
    cwd: Path,
    *,
    active_skills: list[str] | None,
    memory_block: "Any | None",
    session: SessionRuntime,
    agent_name: str | None = None,
) -> tuple[str, list[str]]:
    system_prompt, loaded_context = build_system_prompt(
        cwd,
        active_skills=active_skills,
        agent_name=agent_name,
        dev_posture=uses_dev_posture(active_skills, session.state.metadata),
    )
    if memory_block is not None:
        system_prompt = f"{system_prompt}\n\n{memory_block.text}".strip()
    observations = format_session_observations(session.state.metadata)
    if observations:
        system_prompt = f"{system_prompt}\n\n{observations}".strip()
    return system_prompt, loaded_context


def _run_turn(
    orchestrator: RuntimeOrchestrator,
    session: SessionRuntime,
    entry: ProviderEntry,
    text: str,
    *,
    static_system_prompt: str = "",
    active_skills: list[str] | None = None,
    project_root: Path | None = None,
    tool_router: ToolRouter | None = None,
    history: InMemoryVisibleHistoryStore | None = None,
    session_id: str = "default",
    verbose: bool = False,
    memory_store: MemoryStore | None = None,
    stop_event: threading.Event | None = None,
) -> None:
    # Le system_prompt contient déjà le snapshot mémoire injecté au démarrage
    system_prompt = static_system_prompt

    user_message = Message(
        role=Role.USER,
        content=text,
        created_at=datetime.now(timezone.utc),
    )

    if history is not None:
        history.append(session_id, VisibleHistoryEntry(role="user", content=text))

    log_event("turn_start", {
        "session_id": session_id,
        "cwd": str(Path.cwd()),
        "provider": entry.name,
        "provider_kind": entry.provider,
        "model": entry.model,
        "user_preview": preview(text),
    })

    word = random.choice(_SPINNER_WORDS)
    status = Status(
        f"[dim]{word}…[/]",
        spinner="dots",
        spinner_style="color(208)",
        console=_console,
    )
    status.start()
    streaming_started = {"v": False}

    def on_text_delta(delta: str) -> None:
        if stop_event is not None and stop_event.is_set():
            raise KeyboardInterrupt
        if not streaming_started["v"]:
            status.stop()
            _console.print()
            streaming_started["v"] = True
        print(delta, end="", flush=True)

    def on_tool_start(call: ToolCall) -> None:
        status.stop()
        streaming_started["v"] = False
        verb = _tool_verb(call)
        target = _tool_target(call)
        if project_root is not None and maybe_activate_dev_posture(
            session.state.metadata,
            active_skills,
            call,
            project_root,
        ):
            log_event("posture_switch", {
                "session_id": session_id,
                "posture": session.state.metadata.get("posture"),
                "trigger_tool": call.name,
                "target": preview(target, limit=200),
            })
        log_event("tool_start", {
            "session_id": session_id,
            "tool": call.name,
            "target": preview(target, limit=200),
        })
        if target:
            _console.print(f"\n  [tool.bullet]●[/] [tool.verb]{verb}[/]  [tool.target]{target}[/]")
        else:
            _console.print(f"\n  [tool.bullet]●[/] [tool.verb]{verb}[/]")

    def on_tool_result(call: ToolCall, result: ToolResult) -> None:
        observe_tool_result(session.state.metadata, call, result, project_root=project_root)
        style = "tool.ok" if result.ok else "tool.err"
        label = "ok" if result.ok else "erreur"
        log_event("tool_result", {
            "session_id": session_id,
            "tool": call.name,
            "ok": result.ok,
            "summary_preview": preview(result.summary, limit=300),
            "error": preview(result.error or "", limit=300),
        })
        _console.print(f"    [{style}]{label}[/]")

        if verbose and result.summary:
            snippet = result.summary[:_VERBOSE_SUMMARY_MAX]
            if len(result.summary) > _VERBOSE_SUMMARY_MAX:
                snippet += "…"
            quoted = "\n".join(f"> {line}" for line in snippet.splitlines()) or "> …"
            _console.print(Markdown(quoted))

        if history is not None:
            verb = _tool_verb(call)
            target = _tool_target(call)
            trace = f"● {verb}  {target}" if target else f"● {verb}"
            history.append(
                session_id,
                VisibleHistoryEntry(
                    role="tool",
                    content=trace,
                    metadata={
                        "tool_name": call.name,
                        "target": target,
                        "ok": result.ok,
                        "summary": result.summary[:500],
                    },
                ),
            )

    try:
        turn_output = orchestrator.run_turn(
            TurnInput(
                session=session,
                user_message=user_message,
                system_prompt=system_prompt,
            ),
            on_text_delta=on_text_delta,
            on_tool_start=on_tool_start,
            on_tool_result=on_tool_result,
        )
    except ProviderError as exc:
        status.stop()
        log_event("provider_error", {
            "session_id": session_id,
            "provider": entry.name,
            "provider_kind": entry.provider,
            "model": entry.model,
            "retryable": exc.retryable,
            "error": str(exc),
            "provider_name": exc.provider_name,
        })
        _console.print(f"\n[error]  Erreur provider : {exc}[/]\n")
        return
    except Exception as exc:
        status.stop()
        log_event("turn_unexpected_error", {
            "session_id": session_id,
            "provider": entry.name,
            "model": entry.model,
            "error": str(exc),
            "error_type": type(exc).__name__,
        })
        _console.print(f"\n[error]  Erreur inattendue : {exc}[/]\n")
        return
    finally:
        status.stop()

    if turn_output.assistant_message:
        assistant_content = turn_output.assistant_message.content
        rendered_output = render_turn_output(
            replace(turn_output.assistant_message, content="") if streaming_started["v"] else turn_output.assistant_message,
            tool_results=turn_output.tool_results,
            compaction_notice=turn_output.compaction_notice,
            surface=RenderSurface.CLI,
        )
        event_name = "turn_empty_response" if not assistant_content.strip() else "turn_done"
        log_event(event_name, {
            "session_id": session_id,
            "provider": entry.name,
            "provider_kind": entry.provider,
            "model": entry.model,
            "streaming_started": streaming_started["v"],
            "tool_results": len(turn_output.tool_results),
            "assistant_preview": preview(assistant_content),
            "input_tokens": turn_output.usage.provider_input_tokens,
            "estimated_input_tokens": turn_output.usage.estimated_input_tokens,
        })
        if streaming_started["v"]:
            # Les tokens ont déjà été affichés en streaming — juste un saut de ligne
            _console.print("\n")
            if rendered_output:
                _console.print(Markdown(rendered_output))
                _console.print()
        else:
            # Pas de streaming (pas de on_text_delta ou provider sans stream())
            _console.print()
            _console.print(Markdown(rendered_output))
            _console.print()
        if history is not None:
            visible_content = rendered_output
            if streaming_started["v"]:
                visible_content = assistant_content
                if rendered_output:
                    visible_content = f"{assistant_content}\n\n{rendered_output}".strip()
            history.append(
                session_id,
                VisibleHistoryEntry(
                    role="assistant",
                    content=visible_content,
                ),
            )

    # Auto-compaction silencieuse si >= 80% de la fenêtre
    tokens = resolve_token_count(turn_output.usage)
    if tokens > 0:
        _maybe_auto_compact(session, orchestrator, entry, tokens)


# ── point d'entrée ────────────────────────────────────────────────────────────
