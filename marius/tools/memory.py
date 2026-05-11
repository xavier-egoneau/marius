"""Outil mémoire — l'agent écrit et gère ses souvenirs.

Inspiré de Hermes memory_tool.py.
L'agent appelle ce tool proactivement — pas seulement quand l'utilisateur demande.
"""

from __future__ import annotations

from pathlib import Path

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.storage.memory_store import MemoryStore

_MEMORY_SCHEMA = {
    "type": "object",
    "properties": {
        "action": {
            "type": "string",
            "enum": ["add", "replace", "remove", "search", "list", "get"],
            "description": "Action à effectuer.",
        },
        "target": {
            "type": "string",
            "enum": ["agent", "user"],
            "description": (
                "'agent' : notes personnelles (faits d'environnement, conventions projet, "
                "quirks d'outils, leçons apprises). "
                "'user' : profil utilisateur (préférences, corrections, style, pet peeves)."
            ),
        },
        "content": {
            "type": "string",
            "description": "Contenu à mémoriser. Requis pour 'add' et 'replace'.",
        },
        "old_text": {
            "type": "string",
            "description": (
                "Sous-chaîne unique identifiant l'entrée à remplacer ou supprimer. "
                "Requis pour 'replace' et 'remove'."
            ),
        },
        "query": {
            "type": "string",
            "description": "Recherche plein texte. Requis pour 'search'.",
        },
        "memory_id": {
            "type": "integer",
            "description": "Identifiant du souvenir. Requis pour 'get'.",
        },
        "limit": {
            "type": "integer",
            "description": "Nombre maximum de souvenirs à retourner pour 'search' ou 'list'.",
        },
    },
    "required": ["action"],
}

_MEMORY_DESCRIPTION = """\
Mémorise des informations durables sans échéance temporelle.

QUAND UTILISER :
- L'utilisateur partage une préférence, habitude, correction ("ne fais plus ça", "j'aime X")
- L'utilisateur donne une info personnelle utile sur le long terme
- Tu découvres un fait stable sur l'environnement ou le projet

NE PAS UTILISER pour les rappels à heure précise — utilise l'outil `reminders` à la place.

DEUX CIBLES :
- 'user'  : préférences, corrections, infos personnelles
- 'agent' : faits techniques, conventions projet, leçons apprises

ACTIONS :
- add     : nouvelle entrée
- replace : mettre à jour (old_text identifie l'entrée par sous-chaîne)
- remove  : supprimer (old_text identifie l'entrée par sous-chaîne)
- search  : rechercher dans la mémoire durable
- list    : lister les souvenirs récents
- get     : lire un souvenir par identifiant

NE PAS MÉMORISER : état en cours, tâches temporaires, résultats de session.\
"""

_CATEGORY_MAP = {
    "agent": "agent_notes",
    "user": "user_profile",
}


def make_memory_tool(store: MemoryStore, cwd: Path) -> ToolEntry:
    """Crée un ToolEntry mémoire avec le store et le CWD injectés."""

    def handler(arguments: dict) -> ToolResult:
        action = arguments.get("action", "")
        target = arguments.get("target", "")
        content = (arguments.get("content") or "").strip()
        old_text = (arguments.get("old_text") or "").strip()
        query = (arguments.get("query") or "").strip()
        limit = _bounded_limit(arguments.get("limit"))

        if target and target not in ("agent", "user"):
            return ToolResult(tool_call_id="", ok=False, summary=f"Cible invalide : {target!r}. Utiliser 'agent' ou 'user'.")

        category = _CATEGORY_MAP.get(target)

        if action == "add":
            if target not in ("agent", "user"):
                return ToolResult(tool_call_id="", ok=False, summary="'target' requis pour 'add' : agent ou user.")
            if not content:
                return ToolResult(tool_call_id="", ok=False, summary="'content' requis pour 'add'.")
            try:
                memory_id = store.add(content, scope="global", category=category or "")
                return ToolResult(
                    tool_call_id="",
                    ok=True,
                    summary=f"Mémorisé dans {target} (#{memory_id}).",
                    data={"memory_id": memory_id, "target": target},
                )
            except ValueError as exc:
                return ToolResult(tool_call_id="", ok=False, summary=str(exc))

        if action == "replace":
            if target not in ("agent", "user"):
                return ToolResult(tool_call_id="", ok=False, summary="'target' requis pour 'replace' : agent ou user.")
            if not old_text or not content:
                return ToolResult(tool_call_id="", ok=False, summary="'old_text' et 'content' requis pour 'replace'.")
            if store.replace(old_text, content):
                return ToolResult(tool_call_id="", ok=True, summary=f"Entrée mise à jour dans {target}.")
            return ToolResult(tool_call_id="", ok=False, summary=f"Aucune entrée trouvée contenant : {old_text!r}")

        if action == "remove":
            if target not in ("agent", "user"):
                return ToolResult(tool_call_id="", ok=False, summary="'target' requis pour 'remove' : agent ou user.")
            if not old_text:
                return ToolResult(tool_call_id="", ok=False, summary="'old_text' requis pour 'remove'.")
            if store.remove_by_text(old_text):
                return ToolResult(tool_call_id="", ok=True, summary=f"Entrée supprimée de {target}.")
            return ToolResult(tool_call_id="", ok=False, summary=f"Aucune entrée trouvée contenant : {old_text!r}")

        if action == "search":
            if not query:
                return ToolResult(tool_call_id="", ok=False, summary="'query' requis pour 'search'.")
            entries = store.search(query, category=category, limit=limit)
            return _entries_result(entries, "Recherche mémoire")

        if action == "list":
            entries = store.list(category=category, limit=limit)
            return _entries_result(entries, "Souvenirs récents")

        if action == "get":
            memory_id = arguments.get("memory_id")
            if not isinstance(memory_id, int):
                return ToolResult(tool_call_id="", ok=False, summary="'memory_id' entier requis pour 'get'.")
            entry = store.get(memory_id)
            if entry is None:
                return ToolResult(tool_call_id="", ok=False, summary=f"Souvenir introuvable : #{memory_id}", error="memory_not_found")
            return _entries_result([entry], "Souvenir")

        return ToolResult(tool_call_id="", ok=False, summary=f"Action inconnue : {action!r}.")

    return ToolEntry(
        definition=ToolDefinition(
            name="memory",
            description=_MEMORY_DESCRIPTION,
            parameters=_MEMORY_SCHEMA,
        ),
        handler=handler,
    )


def _bounded_limit(value: object, default: int = 10, maximum: int = 50) -> int:
    if not isinstance(value, int):
        return default
    return max(1, min(value, maximum))


def _entries_result(entries: list, title: str) -> ToolResult:
    if not entries:
        return ToolResult(tool_call_id="", ok=True, summary=f"{title} : aucun résultat.", data={"memories": []})

    lines = [f"{title} :"]
    data = []
    for entry in entries:
        lines.append(f"- #{entry.id} [{entry.scope}/{entry.category}] {entry.content}")
        data.append(
            {
                "memory_id": entry.id,
                "content": entry.content,
                "scope": entry.scope,
                "project_path": entry.project_path,
                "category": entry.category,
                "tags": entry.tags,
                "created_at": entry.created_at,
            }
        )
    return ToolResult(tool_call_id="", ok=True, summary="\n".join(lines), data={"memories": data})
