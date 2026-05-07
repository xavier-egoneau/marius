"""Vue persistée de l'historique visible utilisateur.

Ce store est distinct du contexte interne compactable.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class VisibleHistoryEntry:
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)
