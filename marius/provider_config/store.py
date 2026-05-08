"""Persistance des providers dans ~/.marius/marius_providers.json."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .contracts import ProviderEntry

DEFAULT_PROVIDERS_PATH = Path.home() / ".marius" / "marius_providers.json"


class ProviderStore:
    """Lecture et écriture de la liste de providers configurés."""

    def __init__(self, path: Path = DEFAULT_PROVIDERS_PATH) -> None:
        self.path = path

    def load(self) -> list[ProviderEntry]:
        if not self.path.exists():
            return []
        raw: list[dict[str, Any]] = json.loads(self.path.read_text(encoding="utf-8"))
        return [_from_dict(d) for d in raw]

    def save(self, entries: list[ProviderEntry]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps([_to_dict(e) for e in entries], indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add(self, entry: ProviderEntry) -> None:
        entries = self.load()
        entries.append(entry)
        self.save(entries)

    def update(self, entry: ProviderEntry) -> bool:
        """Met à jour un entry existant par id. Retourne True si trouvé."""
        entries = self.load()
        for i, e in enumerate(entries):
            if e.id == entry.id:
                entries[i] = entry
                self.save(entries)
                return True
        return False


def _to_dict(entry: ProviderEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "name": entry.name,
        "provider": entry.provider,
        "auth_type": entry.auth_type,
        "base_url": entry.base_url,
        "api_key": entry.api_key,
        "model": entry.model,
        "added_at": entry.added_at,
        "metadata": entry.metadata,
    }


def _from_dict(data: dict[str, Any]) -> ProviderEntry:
    return ProviderEntry(
        id=data["id"],
        name=data["name"],
        provider=data["provider"],
        auth_type=data["auth_type"],
        base_url=data.get("base_url", ""),
        api_key=data.get("api_key", ""),
        model=data.get("model", ""),
        added_at=data.get("added_at", ""),
        metadata=data.get("metadata", {}),
    )
