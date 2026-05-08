"""Routeur d'outils du kernel Marius.

Brique standalone : déclare les outils, les expose au provider et dispatche
les appels vers les handlers concrets.
"""

from __future__ import annotations

import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from .contracts import Artifact, ToolCall, ToolResult

ToolHandler = Callable[[dict[str, Any]], ToolResult]


@dataclass(frozen=True)
class ToolDefinition:
    """Schéma d'un outil exposé au LLM."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolEntry:
    definition: ToolDefinition
    handler: ToolHandler


class ToolRouter:
    """Registre et dispatcher d'outils.

    Utilisage minimal :
        router = ToolRouter([ToolEntry(defn, handler), ...])
        result = router.dispatch(tool_call)

    Avec garde de permissions :
        router = ToolRouter(entries, guard=PermissionGuard(mode, cwd, on_ask=...))
    """

    def __init__(self, tools: list[ToolEntry], *, guard: "Any | None" = None) -> None:
        self._tools: dict[str, ToolEntry] = {t.definition.name: t for t in tools}
        self._guard = guard

    def definitions(self) -> list[ToolDefinition]:
        """Retourne les définitions à envoyer au provider."""
        return [entry.definition for entry in self._tools.values()]

    def get(self, name: str) -> ToolEntry | None:
        return self._tools.get(name)

    def dispatch(self, call: ToolCall) -> ToolResult:
        """Exécute l'outil désigné par `call`.

        Vérifie le guard de permissions avant d'exécuter.
        Capture toute exception → ToolResult(ok=False) pour que le LLM
        puisse observer l'échec et adapter sa stratégie.
        """
        entry = self._tools.get(call.name)
        if entry is None:
            return ToolResult(
                tool_call_id=call.id,
                ok=False,
                summary=f"Outil inconnu : {call.name!r}",
                error=f"no_tool:{call.name}",
            )

        # Vérification des permissions
        if self._guard is not None and not self._guard.check(call.name, call.arguments):
            return ToolResult(
                tool_call_id=call.id,
                ok=False,
                summary=f"Action refusée : {call.name!r} non autorisé dans ce mode.",
                error="permission_denied",
            )

        try:
            return entry.handler(call.arguments)
        except Exception as exc:
            return ToolResult(
                tool_call_id=call.id,
                ok=False,
                summary=f"Erreur lors de l'exécution de {call.name!r} : {exc}",
                error=traceback.format_exc(),
            )

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools
