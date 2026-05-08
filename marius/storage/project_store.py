"""Registre des projets récemment ouverts.

Brique standalone — dépend uniquement de la stdlib.
Chemin par défaut : ~/.marius/projects.json
"""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

_MARIUS_HOME = Path.home() / ".marius"


@dataclass
class ProjectEntry:
    path: str
    name: str
    last_opened: str
    session_count: int


class ProjectStore:
    """Registre JSON thread-safe des projets récemment ouverts.

    Mis à jour à chaque démarrage REPL via `record_open()`.
    Source de vérité pour le dreaming : quels projets inspecter.
    """

    def __init__(self, store_path: Path | None = None) -> None:
        self._path = Path(store_path) if store_path else _MARIUS_HOME / "projects.json"
        self._lock = threading.Lock()

    def record_open(self, cwd: Path) -> ProjectEntry:
        """Enregistre ou met à jour l'entrée pour `cwd`. Retourne l'entrée finale."""
        resolved = cwd.expanduser().resolve()
        now = datetime.now(timezone.utc).isoformat()

        with self._lock:
            entries = self._load_raw()
            key = str(resolved)
            existing = next((e for e in entries if e["path"] == key), None)

            if existing is not None:
                existing["last_opened"] = now
                existing["session_count"] = existing.get("session_count", 0) + 1
                entry = existing
            else:
                entry = {
                    "path": key,
                    "name": resolved.name,
                    "last_opened": now,
                    "session_count": 1,
                }
                entries.append(entry)

            self._save_raw(entries)

        return ProjectEntry(
            path=entry["path"],
            name=entry["name"],
            last_opened=entry["last_opened"],
            session_count=entry["session_count"],
        )

    def load(self) -> list[ProjectEntry]:
        """Retourne tous les projets, triés par last_opened décroissant."""
        with self._lock:
            raw = self._load_raw()
        return sorted(
            (
                ProjectEntry(
                    path=e["path"],
                    name=e.get("name", Path(e["path"]).name),
                    last_opened=e.get("last_opened", ""),
                    session_count=e.get("session_count", 0),
                )
                for e in raw
            ),
            key=lambda e: e.last_opened,
            reverse=True,
        )

    def get(self, cwd: Path) -> ProjectEntry | None:
        """Retourne l'entrée pour `cwd`, ou None si inconnue."""
        key = str(cwd.expanduser().resolve())
        with self._lock:
            raw = self._load_raw()
        for e in raw:
            if e["path"] == key:
                return ProjectEntry(
                    path=e["path"],
                    name=e.get("name", Path(e["path"]).name),
                    last_opened=e.get("last_opened", ""),
                    session_count=e.get("session_count", 0),
                )
        return None

    def _load_raw(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return data if isinstance(data, list) else []
        except (json.JSONDecodeError, OSError):
            return []

    def _save_raw(self, entries: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
