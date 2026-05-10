"""Store de rappels planifiés.

Persisté en JSON dans le workspace de l'agent.
Un rappel = un texte + une heure de déclenchement + le canal de livraison.
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class Reminder:
    id: str
    text: str
    remind_at: str            # ISO 8601 UTC
    fired: bool = False
    chat_id: int | None = None     # Telegram chat_id pour la livraison
    created_at: str = ""
    fired_at: str | None = None


class RemindersStore:
    """Persistance JSON des rappels planifiés. Thread-safe."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()

    def load(self) -> list[Reminder]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            return [
                Reminder(**{k: v for k, v in r.items() if k in Reminder.__dataclass_fields__})
                for r in data.get("reminders", [])
            ]
        except (json.JSONDecodeError, TypeError, OSError):
            return []

    def _save(self, reminders: list[Reminder]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({"reminders": [asdict(r) for r in reminders]}, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def add(self, text: str, remind_at: datetime, chat_id: int | None = None) -> Reminder:
        with self._lock:
            reminder = Reminder(
                id=uuid.uuid4().hex[:8],
                text=text,
                remind_at=remind_at.astimezone(timezone.utc).isoformat(),
                chat_id=chat_id,
                created_at=datetime.now(timezone.utc).isoformat(),
            )
            reminders = self.load()
            reminders.append(reminder)
            self._save(reminders)
            return reminder

    def due(self, now: datetime | None = None) -> list[Reminder]:
        t = now or datetime.now(timezone.utc)
        return [r for r in self.load() if not r.fired and _parse_dt(r.remind_at) <= t]

    def mark_fired(self, reminder_id: str) -> None:
        with self._lock:
            reminders = self.load()
            for r in reminders:
                if r.id == reminder_id:
                    r.fired = True
                    r.fired_at = datetime.now(timezone.utc).isoformat()
            self._save(reminders)

    def list_pending(self) -> list[Reminder]:
        return [r for r in self.load() if not r.fired]


def _parse_dt(iso: str) -> datetime:
    from marius.kernel.time_utils import parse_stored_dt
    return parse_stored_dt(iso)


def parse_remind_at(value: str) -> datetime:
    """Convertit une expression temporelle en prochain datetime UTC.

    Formats acceptés :
    - Relatif   : "20m", "2h", "1d"
    - Heure     : "08:00", "2h30", "2H30", "14:30"
    - ISO       : "2026-05-10T14:30:00"
    """
    import re
    value = value.strip()

    # Relatif : 20m, 2h, 1d
    m = re.fullmatch(r"(\d+)(m|h|d)", value.lower())
    if m:
        amount = int(m.group(1))
        seconds = amount * {"m": 60, "h": 3600, "d": 86400}[m.group(2)]
        return datetime.now(timezone.utc) + timedelta(seconds=seconds)

    # Heure compacte : 2h30, 2H30
    m = re.fullmatch(r"(\d{1,2})[hH](\d{2})?", value)
    if m:
        h, mn = int(m.group(1)), int(m.group(2) or 0)
        return _next_wall_clock(h, mn)

    # Heure avec deux-points : 08:00, 14:30
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", value)
    if m:
        h, mn = int(m.group(1)), int(m.group(2))
        return _next_wall_clock(h, mn)

    # ISO datetime
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.astimezone()
        return dt.astimezone(timezone.utc)
    except ValueError:
        pass

    raise ValueError(f"Format non reconnu : {value!r} — exemples : '14:30', '2h30', '20m', '2h'")


def _next_wall_clock(h: int, mn: int) -> datetime:
    """Prochain occurrence de HH:MM en heure locale, convertie en UTC."""
    if not (0 <= h <= 23 and 0 <= mn <= 59):
        raise ValueError(f"Heure invalide : {h:02d}:{mn:02d}")
    now_local = datetime.now().astimezone()
    candidate = now_local.replace(hour=h, minute=mn, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)
