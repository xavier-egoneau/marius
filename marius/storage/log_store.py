"""Journal local JSONL pour diagnostiquer les sessions Marius.

Brique standalone — dépend uniquement de la stdlib.
Chemin par défaut : ~/.marius/logs/marius.jsonl
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MARIUS_HOME = Path.home() / ".marius"
DEFAULT_LOG_PATH = _MARIUS_HOME / "logs" / "marius.jsonl"


@dataclass(frozen=True)
class LogEntry:
    timestamp: str
    event: str
    data: dict[str, Any]


def log_event(
    event: str,
    data: dict[str, Any] | None = None,
    *,
    log_path: Path | None = None,
) -> None:
    """Ajoute un événement au journal.

    Le logging ne doit jamais casser l'expérience utilisateur : toute erreur
    d'écriture est volontairement silencieuse.
    """
    path = Path(log_path) if log_path is not None else DEFAULT_LOG_PATH
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "data": _jsonable(data or {}),
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError:
        pass


def read_logs(
    *,
    limit: int = 80,
    log_path: Path | None = None,
) -> list[LogEntry]:
    """Retourne les dernières entrées lisibles du journal."""
    path = Path(log_path) if log_path is not None else DEFAULT_LOG_PATH
    if limit <= 0 or not path.exists():
        return []

    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []

    entries: list[LogEntry] = []
    for line in lines[-limit:]:
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        timestamp = str(raw.get("timestamp") or "")
        event = str(raw.get("event") or "")
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        if timestamp and event:
            entries.append(LogEntry(timestamp=timestamp, event=event, data=data))
    return entries


def clear_logs(*, log_path: Path | None = None) -> None:
    path = Path(log_path) if log_path is not None else DEFAULT_LOG_PATH
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
    except OSError:
        pass


def log_path() -> Path:
    return DEFAULT_LOG_PATH


def preview(text: str, *, limit: int = 300) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: max(0, limit - 1)] + "…"


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_jsonable(v) for v in value]
        return str(value)
