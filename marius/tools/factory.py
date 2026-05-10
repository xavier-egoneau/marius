"""Factory partagée pour la construction du registre d'outils.

Utilisée par le gateway et le REPL pour éviter de dupliquer la logique
de filtrage et d'injection des tools dynamiques (memory, extras).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from marius.tools.filesystem import LIST_DIR, READ_FILE, WRITE_FILE
from marius.tools.shell import RUN_BASH
from marius.tools.skills import SKILL_VIEW
from marius.tools.vision import VISION
from marius.tools.web import WEB_FETCH, WEB_SEARCH

if TYPE_CHECKING:
    from marius.kernel.tool_router import ToolEntry
    from marius.storage.memory_store import MemoryStore

# Registre des outils statiques — partagé entre gateway et REPL
STATIC_ENTRIES: dict[str, "ToolEntry"] = {
    "read_file":  READ_FILE,
    "list_dir":   LIST_DIR,
    "write_file": WRITE_FILE,
    "run_bash":   RUN_BASH,
    "web_fetch":  WEB_FETCH,
    "web_search": WEB_SEARCH,
    "vision":     VISION,
    "skill_view": SKILL_VIEW,
}


def build_tool_entries(
    enabled_tools: list[str] | None,
    memory_store: "MemoryStore",
    cwd: Path,
    *,
    extras: "dict[str, ToolEntry] | None" = None,
) -> "list[ToolEntry]":
    """Construit la liste des ToolEntry actifs pour un agent.

    - enabled_tools=None → tous les outils inclus.
    - memory est toujours présent (injecté en tête si absent).
    - extras : tools supplémentaires toujours injectés (ex: {"reminders": …}).
      Chaque entry dans extras est incluse même si absente de enabled_tools.
    """
    from marius.tools.memory import make_memory_tool

    memory_tool = make_memory_tool(memory_store, cwd)
    _extras: dict[str, ToolEntry] = extras or {}
    registry = {**STATIC_ENTRIES, "memory": memory_tool, **_extras}

    if enabled_tools is None:
        return list(registry.values())

    entries = [registry[name] for name in enabled_tools if name in registry]

    if memory_tool not in entries:
        entries.insert(0, memory_tool)
    for extra in _extras.values():
        if extra not in entries:
            entries.insert(0, extra)

    return entries
