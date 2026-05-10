"""Outil de rappels planifiés.

L'agent appelle create_reminder pour programmer un rappel à une heure précise.
Le gateway livre le rappel via Telegram au moment voulu.
"""

from __future__ import annotations

from pathlib import Path

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.storage.reminders_store import RemindersStore, parse_remind_at

_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {
            "type": "string",
            "description": "Texte du rappel, tel qu'il sera envoyé à l'utilisateur.",
        },
        "remind_at": {
            "type": "string",
            "description": (
                "Moment du déclenchement. Formats acceptés : "
                "'14:30' ou '2h30' (heure locale), '20m' / '2h' / '1d' (délai relatif), "
                "ou ISO datetime complet."
            ),
        },
    },
    "required": ["text", "remind_at"],
}

_DESCRIPTION = """\
Programme un rappel qui sera envoyé à l'utilisateur à l'heure demandée.

Utilise cet outil quand l'utilisateur dit "rappelle moi à X", "rappelle moi de faire Y à Z heures",
"dans 30 minutes rappelle moi", etc.

Exemples de remind_at :
- "14:30"  → aujourd'hui à 14h30 (demain si l'heure est passée)
- "2h30"   → demain à 02h30
- "20m"    → dans 20 minutes
- "2h"     → dans 2 heures
- "1d"     → dans 24 heures\
"""


def make_reminders_tool(store: RemindersStore, get_chat_id=None) -> ToolEntry:
    """Crée un ToolEntry rappels avec le store injecté.

    get_chat_id : callable() → int | None, retourne le chat_id Telegram courant.
    """

    def handler(arguments: dict) -> ToolResult:
        text = (arguments.get("text") or "").strip()
        remind_at_raw = (arguments.get("remind_at") or "").strip()

        if not text:
            return ToolResult(tool_call_id="", ok=False, summary="'text' requis.")
        if not remind_at_raw:
            return ToolResult(tool_call_id="", ok=False, summary="'remind_at' requis.")

        try:
            remind_at = parse_remind_at(remind_at_raw)
        except ValueError as exc:
            return ToolResult(tool_call_id="", ok=False, summary=str(exc))

        chat_id = get_chat_id() if get_chat_id is not None else None
        reminder = store.add(text=text, remind_at=remind_at, chat_id=chat_id)

        from datetime import datetime, timezone
        local_time = remind_at.astimezone()
        now_local = datetime.now().astimezone()
        if local_time.date() == now_local.date():
            human = local_time.strftime("%H:%M")
        else:
            human = f"demain à {local_time.strftime('%H:%M')}"

        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Rappel programmé pour {human} : {text}",
            data={"reminder_id": reminder.id, "remind_at": reminder.remind_at},
        )

    return ToolEntry(
        definition=ToolDefinition(
            name="reminders",
            description=_DESCRIPTION,
            parameters=_SCHEMA,
        ),
        handler=handler,
    )
