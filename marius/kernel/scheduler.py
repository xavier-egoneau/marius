"""Scheduler de jobs périodiques pour Marius.

Brique standalone — dépend uniquement de la stdlib.
Persiste les jobs dans un fichier JSON. Reprise transparente après redémarrage.

Usage minimal :
    store = JobStore(path)
    scheduler = Scheduler(store, handlers={"dreaming": fn, "daily": fn})
    scheduler.run_forever()   # dans un thread daemon
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable


@dataclass
class ScheduledJob:
    id: str
    name: str
    run_at: str            # ISO 8601 UTC
    interval_seconds: int  # 86400 = daily
    status: str = "scheduled"     # scheduled | running
    last_run: str | None = None
    last_error: str | None = None


class JobStore:
    """Persistance JSON des jobs planifiés. Thread-safe."""

    def __init__(self, path: Path) -> None:
        self._path = Path(path)
        self._lock = threading.RLock()

    def load(self) -> list[ScheduledJob]:
        if not self._path.exists():
            return []
        try:
            data: dict[str, Any] = json.loads(self._path.read_text(encoding="utf-8"))
            return [
                ScheduledJob(**{k: v for k, v in j.items() if k in ScheduledJob.__dataclass_fields__})
                for j in data.get("jobs", [])
            ]
        except (json.JSONDecodeError, TypeError, OSError):
            return []

    def save(self, jobs: list[ScheduledJob]) -> None:
        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(
                json.dumps({"jobs": [asdict(j) for j in jobs]}, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    def upsert(self, job: ScheduledJob) -> None:
        with self._lock:
            jobs = self.load()
            jobs = [j for j in jobs if j.id != job.id]
            jobs.append(job)
            self.save(jobs)

    def update(self, job: ScheduledJob) -> None:
        with self._lock:
            jobs = self.load()
            self.save([j if j.id != job.id else job for j in jobs])

    def due(self, now: datetime | None = None) -> list[ScheduledJob]:
        """Retourne les jobs dont l'heure est passée."""
        t = now or datetime.now(timezone.utc)
        return [
            j for j in self.load()
            if j.status == "scheduled" and _parse_dt(j.run_at) <= t
        ]

    def list_all(self) -> list[ScheduledJob]:
        return self.load()


class Scheduler:
    """Exécute les jobs dus et les replanifie pour le lendemain."""

    def __init__(
        self,
        store: JobStore,
        handlers: dict[str, Callable[[], None]],
        before_tick: Callable[[], None] | None = None,
    ) -> None:
        self._store = store
        self._handlers = handlers
        self._before_tick = before_tick
        self._stop = threading.Event()

    def tick(self, now: datetime | None = None) -> list[str]:
        """Exécute les jobs dus. Retourne les noms des jobs lancés."""
        if self._before_tick is not None:
            self._before_tick()
        fired: list[str] = []
        for job in self._store.due(now):
            handler = self._handlers.get(job.name)
            if handler is None:
                continue
            job.status = "running"
            self._store.update(job)
            fired.append(job.name)
            try:
                handler()
                job.last_error = None
            except Exception as exc:
                job.last_error = str(exc)
            finally:
                job.status = "scheduled"
                job.last_run = datetime.now(timezone.utc).isoformat()
                job.run_at = _advance_daily(_parse_dt(job.run_at), job.interval_seconds).isoformat()
                self._store.update(job)
        return fired

    def run_forever(self, poll_seconds: float = 60.0) -> None:
        """Boucle de polling. À lancer dans un thread daemon."""
        while not self._stop.wait(poll_seconds):
            try:
                self.tick()
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()


# ── helpers publics ───────────────────────────────────────────────────────────


def next_run_for_time(hhmm: str) -> datetime:
    """Calcule le prochain datetime UTC pour une heure HH:MM locale.

    L'heure est interprétée dans le fuseau horaire de la machine (comme
    l'utilisateur la lit sur son horloge), puis convertie en UTC pour stockage.
    Si l'heure est déjà passée aujourd'hui, planifie pour demain.
    """
    h, m = _parse_hhmm(hhmm)
    now_local = datetime.now().astimezone()   # heure locale avec tz de la machine
    candidate = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def ensure_jobs(
    store: JobStore,
    *,
    dream_time: str = "",
    daily_time: str = "",
) -> None:
    """Crée les jobs dreaming/daily s'ils n'existent pas encore."""
    existing = {j.id for j in store.list_all()}

    if dream_time and "dreaming" not in existing:
        store.upsert(ScheduledJob(
            id="dreaming",
            name="dreaming",
            run_at=next_run_for_time(dream_time).isoformat(),
            interval_seconds=86400,
        ))

    if daily_time and "daily" not in existing:
        store.upsert(ScheduledJob(
            id="daily",
            name="daily",
            run_at=next_run_for_time(daily_time).isoformat(),
            interval_seconds=86400,
        ))


def ensure_watch_jobs(store: JobStore, topics: list[Any]) -> None:
    """Synchronise les jobs watch à partir de topics avec cadence.

    Un topic avec cadence `manual` ou disabled n'est pas planifié. Les jobs
    obsolètes `watch:<id>` sont retirés pour éviter les runs fantômes.
    """
    jobs = store.list_all()
    next_jobs = [job for job in jobs if not job.id.startswith("watch:")]
    existing = {job.id: job for job in jobs if job.id.startswith("watch:")}

    for topic in topics:
        topic_id = str(getattr(topic, "id", "") or "")
        if not topic_id or not bool(getattr(topic, "enabled", True)):
            continue
        cadence = str(getattr(topic, "cadence", "") or "manual")
        interval = cadence_to_seconds(cadence)
        if interval is None:
            continue
        job_id = f"watch:{topic_id}"
        previous = existing.get(job_id)
        if previous and previous.interval_seconds == interval:
            next_jobs.append(previous)
            continue
        next_jobs.append(ScheduledJob(
            id=job_id,
            name=job_id,
            run_at=(datetime.now(timezone.utc) + timedelta(seconds=interval)).isoformat(),
            interval_seconds=interval,
        ))

    store.save(next_jobs)


def cadence_to_seconds(cadence: str) -> int | None:
    """Convertit une cadence watch en secondes, None = manuel/non planifié."""
    raw = (cadence or "manual").strip().lower().replace(" ", "")
    aliases = {
        "manual": None,
        "off": None,
        "disabled": None,
        "hourly": 3600,
        "daily": 86400,
        "weekly": 7 * 86400,
    }
    if raw in aliases:
        return aliases[raw]
    unit = raw[-1:] if raw else ""
    number = raw[:-1]
    if unit in ("m", "h", "d") and number.isdigit():
        value = int(number)
        if value <= 0:
            return None
        if unit == "m":
            return max(60, value * 60)
        if unit == "h":
            return value * 3600
        return value * 86400
    return None

# ── helpers privés ────────────────────────────────────────────────────────────


def _parse_hhmm(hhmm: str) -> tuple[int, int]:
    """Parse HH:MM ou HHhMM. Lève ValueError si le format est invalide."""
    raw = hhmm.strip().replace("h", ":")
    try:
        parts = raw.split(":")
        h, m = int(parts[0]), int(parts[1])
    except (ValueError, IndexError, AttributeError):
        raise ValueError(f"Format d'heure invalide : {hhmm!r} — attendu HH:MM (ex: 09:00)")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Heure hors limites : {hhmm!r}")
    return h, m


def validate_hhmm(hhmm: str) -> str:
    """Valide et normalise une heure HH:MM. Lève ValueError si invalide."""
    h, m = _parse_hhmm(hhmm)
    return f"{h:02d}:{m:02d}"


def _parse_dt(iso: str) -> datetime:
    from marius.kernel.time_utils import parse_stored_dt
    return parse_stored_dt(iso)


def _advance_daily(last: datetime, interval_seconds: int) -> datetime:
    """Avance au prochain slot sans accumulation de retard."""
    now = datetime.now(timezone.utc)
    next_run = last + timedelta(seconds=interval_seconds)
    # Si on a beaucoup de retard, sauter les slots manqués
    while next_run <= now:
        next_run += timedelta(seconds=interval_seconds)
    return next_run
