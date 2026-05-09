"""Parse et application des opérations JSON retournées par le LLM dreaming."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from marius.storage.memory_store import MemoryStore


@dataclass
class DreamingResult:
    added: int = 0
    updated: int = 0
    removed: int = 0
    errors: int = 0
    summary: str = ""
    raw_ops: int = 0

    @property
    def total_ops(self) -> int:
        return self.added + self.updated + self.removed

    def __str__(self) -> str:
        if self.summary:
            return self.summary
        if self.total_ops == 0:
            return "Mémoire à jour — aucune opération effectuée."
        parts = []
        if self.added:
            parts.append(f"{self.added} ajouté(s)")
        if self.updated:
            parts.append(f"{self.updated} mis à jour")
        if self.removed:
            parts.append(f"{self.removed} supprimé(s)")
        if self.errors:
            parts.append(f"{self.errors} erreur(s)")
        return "Dreaming : " + ", ".join(parts) + "."


_JSON_RE = re.compile(r'\{.*\}', re.DOTALL)


def parse_response(response: str) -> tuple[list[dict], str]:
    """Extrait les opérations et le résumé de la réponse LLM.

    Retourne (operations, summary). Tolère du texte autour du JSON.
    """
    m = _JSON_RE.search(response)
    if not m:
        return [], ""
    try:
        data = json.loads(m.group())
    except json.JSONDecodeError:
        return [], ""
    ops = data.get("operations", [])
    summary = data.get("summary", "")
    if not isinstance(ops, list):
        ops = []
    return ops, summary


def apply_operations(
    ops: list[dict],
    memory_store: MemoryStore,
    *,
    project_path: str | None = None,
) -> DreamingResult:
    """Applique les opérations JSON au store. Retourne le bilan."""
    result = DreamingResult(raw_ops=len(ops))

    for op in ops:
        op_type = op.get("op", "")
        try:
            if op_type == "add":
                content = str(op.get("content", "")).strip()
                if not content:
                    result.errors += 1
                    continue
                scope = op.get("scope", "global")
                pp = op.get("project_path") or project_path
                tags = op.get("tags", "")
                memory_store.add(
                    content,
                    scope=scope,
                    project_path=pp if scope == "project" else None,
                    tags=tags,
                )
                result.added += 1

            elif op_type == "replace":
                old = str(op.get("old", "")).strip()
                new = str(op.get("new", "")).strip()
                if not old or not new:
                    result.errors += 1
                    continue
                if memory_store.replace(old, new):
                    result.updated += 1
                else:
                    result.errors += 1

            elif op_type == "remove":
                text = str(op.get("text", "")).strip()
                if not text:
                    result.errors += 1
                    continue
                if memory_store.remove_by_text(text):
                    result.removed += 1
                else:
                    result.errors += 1

            else:
                result.errors += 1

        except Exception:
            result.errors += 1

    return result
