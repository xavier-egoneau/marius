"""Orchestrateur minimal du kernel.

Ce module définit le pipeline logique d'un tour sans dépendre d'un canal concret.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .contracts import ContextUsage, Message, ToolResult


@dataclass(slots=True)
class TurnInput:
    messages: list[Message]
    system_prompt: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TurnOutput:
    assistant_message: Message | None = None
    tool_results: list[ToolResult] = field(default_factory=list)
    usage: ContextUsage = field(default_factory=ContextUsage)
    metadata: dict[str, Any] = field(default_factory=dict)


class RuntimeOrchestrator:
    """Squelette initial du pipeline kernel.

    Le câblage effectif viendra après stabilisation des interfaces des briques.
    """

    def run_turn(self, turn_input: TurnInput) -> TurnOutput:
        return TurnOutput(metadata={"status": "not_implemented", "message_count": len(turn_input.messages)})
