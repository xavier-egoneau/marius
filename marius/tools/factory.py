"""Factory partagée pour la construction du registre d'outils.

Utilisée par le gateway et le REPL pour éviter de dupliquer la logique
de filtrage et d'injection des tools dynamiques (memory, extras).
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from marius.provider_config.contracts import ProviderEntry
    from marius.kernel.tool_router import ToolEntry
    from marius.storage.memory_store import MemoryStore

STATIC_TOOL_NAMES: list[str] = [
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
    "self_update_propose",
    "self_update_report_bug",
    "self_update_list",
    "self_update_show",
    "self_update_apply",
    "self_update_rollback",
    "open_marius_web",
    "caldav_doctor",
    "caldav_agenda",
    "caldav_maintenance",
]

FACTORY_TOOL_NAMES: list[str] = [
    *STATIC_TOOL_NAMES,
    "project_list",
    "project_set_active",
    "dreaming_run",
    "rag_source_add",
    "rag_source_list",
    "rag_source_sync",
    "rag_search",
    "rag_get",
    "rag_promote_to_memory",
    "rag_checklist_add",
    "sentinelle_scan",
    "task_create",
    "task_list",
    "task_update",
    "reminders",
    "browser_open",
    "browser_extract",
    "browser_screenshot",
    "browser_click",
    "browser_type",
    "browser_close",
    "spawn_agent",
    "call_agent",
]


def registered_tool_names() -> list[str]:
    """Return the user-configurable tool registry names in runtime order."""
    return list(FACTORY_TOOL_NAMES)


class _LazyStaticEntries(Mapping[str, "ToolEntry"]):
    def __iter__(self) -> Iterator[str]:
        return iter(STATIC_TOOL_NAMES)

    def __len__(self) -> int:
        return len(STATIC_TOOL_NAMES)

    def __getitem__(self, key: str) -> "ToolEntry":
        return _static_entries()[key]

    def keys(self):
        return STATIC_TOOL_NAMES


STATIC_ENTRIES: Mapping[str, "ToolEntry"] = _LazyStaticEntries()


def _static_entries() -> dict[str, "ToolEntry"]:
    from marius.tools.caldav_calendar import CALDAV_AGENDA, CALDAV_DOCTOR, CALDAV_MAINTENANCE
    from marius.tools.explore import EXPLORE_GREP, EXPLORE_SUMMARY, EXPLORE_TREE
    from marius.tools.filesystem import LIST_DIR, MAKE_DIR, MOVE_PATH, READ_FILE, WRITE_FILE
    from marius.tools.host_admin import (
        HOST_AGENT_DELETE,
        HOST_AGENT_LIST,
        HOST_AGENT_SAVE,
        HOST_DOCTOR,
        HOST_GATEWAY_RESTART,
        HOST_LOGS,
        HOST_STATUS,
        HOST_TELEGRAM_CONFIGURE,
    )
    from marius.tools.marius_web import OPEN_MARIUS_WEB
    from marius.tools.provider_admin import PROVIDER_DELETE, PROVIDER_LIST, PROVIDER_MODELS, PROVIDER_SAVE
    from marius.tools.security_admin import (
        APPROVAL_DECIDE,
        APPROVAL_FORGET,
        APPROVAL_LIST,
        SECRET_REF_DELETE,
        SECRET_REF_LIST,
        SECRET_REF_PREPARE_FILE,
        SECRET_REF_SAVE,
    )
    from marius.tools.self_update import (
        SELF_UPDATE_APPLY,
        SELF_UPDATE_LIST,
        SELF_UPDATE_PROPOSE,
        SELF_UPDATE_REPORT_BUG,
        SELF_UPDATE_ROLLBACK,
        SELF_UPDATE_SHOW,
    )
    from marius.tools.shell import RUN_BASH
    from marius.tools.skill_authoring import SKILL_CREATE, SKILL_LIST, SKILL_RELOAD
    from marius.tools.skills import SKILL_VIEW
    from marius.tools.vision import VISION
    from marius.tools.web import WEB_FETCH, WEB_SEARCH

    return {
        "read_file": READ_FILE,
        "list_dir": LIST_DIR,
        "write_file": WRITE_FILE,
        "make_dir": MAKE_DIR,
        "move_path": MOVE_PATH,
        "explore_tree": EXPLORE_TREE,
        "explore_grep": EXPLORE_GREP,
        "explore_summary": EXPLORE_SUMMARY,
        "run_bash": RUN_BASH,
        "web_fetch": WEB_FETCH,
        "web_search": WEB_SEARCH,
        "vision": VISION,
        "skill_view": SKILL_VIEW,
        "skill_create": SKILL_CREATE,
        "skill_list": SKILL_LIST,
        "skill_reload": SKILL_RELOAD,
        "host_agent_list": HOST_AGENT_LIST,
        "host_agent_save": HOST_AGENT_SAVE,
        "host_agent_delete": HOST_AGENT_DELETE,
        "host_telegram_configure": HOST_TELEGRAM_CONFIGURE,
        "host_status": HOST_STATUS,
        "host_doctor": HOST_DOCTOR,
        "host_logs": HOST_LOGS,
        "host_gateway_restart": HOST_GATEWAY_RESTART,
        "approval_list": APPROVAL_LIST,
        "approval_decide": APPROVAL_DECIDE,
        "approval_forget": APPROVAL_FORGET,
        "secret_ref_list": SECRET_REF_LIST,
        "secret_ref_save": SECRET_REF_SAVE,
        "secret_ref_delete": SECRET_REF_DELETE,
        "secret_ref_prepare_file": SECRET_REF_PREPARE_FILE,
        "provider_list": PROVIDER_LIST,
        "provider_save": PROVIDER_SAVE,
        "provider_delete": PROVIDER_DELETE,
        "provider_models": PROVIDER_MODELS,
        "self_update_propose": SELF_UPDATE_PROPOSE,
        "self_update_report_bug": SELF_UPDATE_REPORT_BUG,
        "self_update_list": SELF_UPDATE_LIST,
        "self_update_show": SELF_UPDATE_SHOW,
        "self_update_apply": SELF_UPDATE_APPLY,
        "self_update_rollback": SELF_UPDATE_ROLLBACK,
        "open_marius_web": OPEN_MARIUS_WEB,
        "caldav_doctor": CALDAV_DOCTOR,
        "caldav_agenda": CALDAV_AGENDA,
        "caldav_maintenance": CALDAV_MAINTENANCE,
    }


def build_tool_entries(
    enabled_tools: list[str] | None,
    memory_store: "MemoryStore",
    cwd: Path,
    *,
    entry: "ProviderEntry | None" = None,
    active_skills: list[str] | None = None,
    agent_name: str | None = None,
    reminders_store: object | None = None,
    get_reminder_chat_id: object | None = None,
    permission_mode: str = "limited",
    extras: "dict[str, ToolEntry] | None" = None,
) -> "list[ToolEntry]":
    """Construit la liste des ToolEntry actifs pour un agent.

    - enabled_tools=None → tous les outils inclus.
    - memory est toujours présent (injecté en tête si absent).
    - entry : provider courant, nécessaire aux outils dynamiques de dreaming/spawn.
    - reminders_store : store courant, nécessaire à l'outil reminders.
    - extras : tools supplémentaires hors catalogue, réservés aux tests/injections ponctuelles.
      Chaque entry dans extras est incluse même si absente de enabled_tools.
    """
    from marius.tools.browser import make_browser_tools
    from marius.tools.call_agent import make_call_agent_tool
    from marius.tools.memory import make_memory_tool
    from marius.tools.projects import make_project_tools
    from marius.tools.rag import make_rag_tools
    from marius.tools.reminders import make_reminders_tool
    from marius.tools.sentinelle import make_sentinelle_tool
    from marius.tools.spawn_agent import make_spawn_agent_tool
    from marius.tools.tasks import make_task_tools

    enabled_set = None if enabled_tools is None else set(enabled_tools)
    memory_tool = make_memory_tool(memory_store, cwd)
    workspace_root = Path.home() / ".marius" / "workspace" / (agent_name or "main")
    rag_tools = make_rag_tools(workspace_root / "skills" / "rag", memory_store=memory_store, cwd=cwd)
    sentinelle_tool = make_sentinelle_tool(workspace_root / "sentinelle")
    project_tools = make_project_tools(
        cwd=cwd,
        allow_store_path=Path.home() / ".marius" / "allowed_roots.json",
    )
    task_tools = make_task_tools()
    browser_tools = make_browser_tools(cwd)
    dreaming_tools: dict[str, ToolEntry] = {}
    if entry is not None:
        from marius.tools.dreaming import make_dreaming_tools
        dreaming_tools = make_dreaming_tools(
            memory_store=memory_store,
            entry=entry,
            project_root=cwd,
            active_skills=active_skills,
        )
    if reminders_store is None:
        from marius.gateway.workspace import reminders_path
        from marius.storage.reminders_store import RemindersStore
        reminders_store = RemindersStore(reminders_path(agent_name or "main"))
    reminder_tools: dict[str, ToolEntry] = {
        "reminders": make_reminders_tool(reminders_store, get_chat_id=get_reminder_chat_id)
    }
    _extras: dict[str, ToolEntry] = extras or {}
    registry = {
        **_static_entries(),
        **rag_tools,
        **task_tools,
        **browser_tools,
        **reminder_tools,
        "sentinelle_scan": sentinelle_tool,
        **project_tools,
        **dreaming_tools,
        "memory": memory_tool,
    }

    if enabled_tools is None:
        entries = list(registry.values())
    else:
        entries = [registry[name] for name in enabled_tools if name in registry]

    if memory_tool not in entries:
        entries.insert(0, memory_tool)

    if entry is not None and (enabled_set is None or "spawn_agent" in enabled_set):
        spawn_tool = make_spawn_agent_tool(
            entry,
            entries,
            permission_mode=permission_mode,
            cwd=cwd,
        )
        entries.append(spawn_tool)

    if enabled_set is None or "call_agent" in enabled_set:
        entries.append(make_call_agent_tool())

    for extra in _extras.values():
        if extra not in entries:
            entries.insert(0, extra)

    return entries
