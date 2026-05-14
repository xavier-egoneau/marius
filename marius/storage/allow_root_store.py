"""Allow-list persistante des racines validées par le gardien."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

_MARIUS_HOME = Path.home() / ".marius"


@dataclass(frozen=True)
class AllowedRoot:
    path: str
    reason: str
    added_at: str


class AllowRootStore:
    """Stockage JSON thread-safe des racines de confiance."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else _MARIUS_HOME / "allowed_roots.json"
        self._lock = threading.Lock()

    def list(self) -> list[AllowedRoot]:
        with self._lock:
            raw = self._load_raw()
        return [
            AllowedRoot(
                path=str(entry.get("path") or ""),
                reason=str(entry.get("reason") or ""),
                added_at=str(entry.get("added_at") or ""),
            )
            for entry in raw
            if str(entry.get("path") or "").strip()
        ]

    def paths(self) -> tuple[Path, ...]:
        return tuple(Path(entry.path) for entry in self.list())

    def add(self, root: Path, *, reason: str) -> AllowedRoot:
        resolved = root.expanduser().resolve(strict=False)
        now = datetime.now(timezone.utc).isoformat()
        with self._lock:
            raw = self._load_raw()
            key = str(resolved)
            for entry in raw:
                if entry.get("path") == key:
                    return AllowedRoot(
                        path=key,
                        reason=str(entry.get("reason") or ""),
                        added_at=str(entry.get("added_at") or ""),
                    )

            entry = AllowedRoot(path=key, reason=reason, added_at=now)
            raw.append(asdict(entry))
            self._save_raw(raw)
            return entry

    def _load_raw(self) -> list[dict]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        return data if isinstance(data, list) else []

    def _save_raw(self, entries: list[dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(entries, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
