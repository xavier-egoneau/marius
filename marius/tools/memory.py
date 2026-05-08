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
            "enum": ["add", "replace", "remove"],
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
    },
    "required": ["action", "target"],
}

_MEMORY_DESCRIPTION = """\
Mémorise des informations durables qui seront utiles dans les prochaines sessions.

QUAND UTILISER (de façon proactive, sans attendre qu'on le demande) :
- L'utilisateur te corrige ou dit "souviens-toi" / "ne fais plus ça"
- L'utilisateur partage une préférence, habitude ou info personnelle
- Tu découvres un fait sur l'environnement (OS, outils installés, structure projet)
- Tu apprends une convention, un quirk d'API ou un workflow propre à cet utilisateur
- Tu identifies un fait stable qui sera utile dans les sessions futures

DEUX CIBLES :
- 'agent' : tes notes personnelles — faits techniques, conventions, leçons apprises
- 'user'  : profil utilisateur — prénom, rôle, préférences, corrections, ce qu'il déteste

ACTIONS :
- add     : nouvelle entrée
- replace : mettre à jour (old_text identifie l'entrée par sous-chaîne)
- remove  : supprimer (old_text identifie l'entrée par sous-chaîne)

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

        if target not in ("agent", "user"):
            return ToolResult(ok=False, summary=f"Cible invalide : {target!r}. Utiliser 'agent' ou 'user'.", data=None)

        category = _CATEGORY_MAP[target]

        if action == "add":
            if not content:
                return ToolResult(ok=False, summary="'content' requis pour 'add'.", data=None)
            try:
                memory_id = store.add(content, scope="global", category=category)
                return ToolResult(
                    ok=True,
                    summary=f"Mémorisé dans {target} (#{memory_id}).",
                    data={"memory_id": memory_id, "target": target},
                )
            except ValueError as exc:
                return ToolResult(ok=False, summary=str(exc), data=None)

        if action == "replace":
            if not old_text or not content:
                return ToolResult(ok=False, summary="'old_text' et 'content' requis pour 'replace'.", data=None)
            if store.replace(old_text, content):
                return ToolResult(ok=True, summary=f"Entrée mise à jour dans {target}.", data=None)
            return ToolResult(ok=False, summary=f"Aucune entrée trouvée contenant : {old_text!r}", data=None)

        if action == "remove":
            if not old_text:
                return ToolResult(ok=False, summary="'old_text' requis pour 'remove'.", data=None)
            if store.remove_by_text(old_text):
                return ToolResult(ok=True, summary=f"Entrée supprimée de {target}.", data=None)
            return ToolResult(ok=False, summary=f"Aucune entrée trouvée contenant : {old_text!r}", data=None)

        return ToolResult(ok=False, summary=f"Action inconnue : {action!r}. Utiliser add, replace ou remove.", data=None)

    return ToolEntry(
        definition=ToolDefinition(
            name="memory",
            description=_MEMORY_DESCRIPTION,
            parameters=_MEMORY_SCHEMA,
        ),
        handler=handler,
    )
