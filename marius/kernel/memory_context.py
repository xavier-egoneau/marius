"""Formatage des souvenirs pour injection dans le system prompt.

Brique pure — aucun I/O, aucune dépendance externe.
Prend une liste de MemoryEntry (duck-typed) et retourne un bloc Markdown.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class _EntryLike(Protocol):
    id: int
    content: str
    category: str
    tags: str


@dataclass(frozen=True)
class MemoryBlock:
    text: str
    count: int


def format_memory_block(entries: list[_EntryLike]) -> MemoryBlock | None:
    """Formate des souvenirs en bloc injecté dans le system prompt.

    Retourne None si la liste est vide.
    Format :
        <memory>
        - contenu  [tags]   ← les tags sont omis s'ils sont vides
        </memory>
    """
    if not entries:
        return None

    lines: list[str] = ["<memory>"]
    for entry in entries:
        tag_suffix = f"  [{entry.tags}]" if entry.tags else ""
        lines.append(f"- {entry.content}{tag_suffix}")
    lines.append("</memory>")

    return MemoryBlock(text="\n".join(lines), count=len(entries))
