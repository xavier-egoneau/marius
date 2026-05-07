"""Vue persistée de l'historique visible utilisateur.

Ce store est distinct du contexte interne compactable.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field, replace
from typing import Any


@dataclass(slots=True)
class VisibleHistoryEntry:
    role: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    artifacts: list[dict[str, Any]] = field(default_factory=list)


class InMemoryVisibleHistoryStore:
    """Store minimal pour l'historique visible, isolé par session."""

    def __init__(self) -> None:
        self._entries_by_session: dict[str, list[VisibleHistoryEntry]] = {}

    def append(self, session_id: str, entry: VisibleHistoryEntry) -> None:
        bucket = self._entries_by_session.setdefault(session_id, [])
        bucket.append(self._clone_entry(entry))

    def list_entries(self, session_id: str) -> list[VisibleHistoryEntry]:
        return [self._clone_entry(entry) for entry in self._entries_by_session.get(session_id, [])]

    @staticmethod
    def _clone_entry(entry: VisibleHistoryEntry) -> VisibleHistoryEntry:
        return replace(
            entry,
            metadata=deepcopy(entry.metadata),
            artifacts=deepcopy(entry.artifacts),
        )
