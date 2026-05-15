"""Outil skill_view pour Marius.

Permet à l'agent de lire le contenu complet d'un skill par son nom.
"""

from __future__ import annotations

from typing import Any

from marius.kernel.contracts import ToolResult
from marius.kernel.skills import SkillReader
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_reader = SkillReader()


def _skill_view(arguments: dict[str, Any]) -> ToolResult:
    name = arguments.get("name", "").strip()
    if not name:
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary="Argument `name` manquant.",
            error="missing_arg:name",
        )
    skill = _reader.load(name)
    if skill is None:
        available = [m.name for m in _reader.list()]
        hint = f"Skills disponibles : {', '.join(available)}" if available else "Aucun skill installé."
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Skill '{name}' introuvable. {hint}",
            error="not_found",
        )
    parts = [skill.content]
    if skill.dream_content:
        parts.append(f"## Contrat dreaming\n{skill.dream_content}")
    for fname, fcontent in skill.core_files.items():
        parts.append(f"## core/{fname}\n{fcontent}")
    full = "\n\n".join(parts)
    return ToolResult(
        tool_call_id="",
        ok=True,
        summary=full,
        data={
            "name": skill.meta.name,
            "description": skill.meta.description,
            "core_files": list(skill.core_files.keys()),
        },
    )


SKILL_VIEW = ToolEntry(
    definition=ToolDefinition(
        name="skill_view",
        description=(
            "Lire le contenu complet d'un skill par son nom. "
            "Utile pour consulter les instructions détaillées d'un skill actif, "
            "ou explorer un skill avant de l'activer."
        ),
        parameters={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nom du skill à lire (ex: 'onboarding', 'dev')",
                }
            },
            "required": ["name"],
        },
    ),
    handler=_skill_view,
)
