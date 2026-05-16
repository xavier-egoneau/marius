"""Scheduler de tâches récurrentes pour Marius.

Lit directement depuis TaskStore — plus de jobs.json intermédiaire.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable


class TaskRunCancelled(Exception):
    """Raised when a running task was manually moved out of execution."""


class TaskScheduler:
    """Exécute les tâches récurrentes en lisant task_store à chaque tick."""

    def __init__(
        self,
        handlers: dict[str, Callable[[], None]],
        before_tick: Callable[[], None] | None = None,
        poll_seconds: float = 60.0,
    ) -> None:
        self._handlers   = handlers
        self._before_tick = before_tick
        self._poll       = poll_seconds
        self._stop       = threading.Event()

    def tick(self) -> list[str]:
        """Exécute les tâches dues. Retourne les IDs lancés."""
        if self._before_tick is not None:
            self._before_tick()

        from marius.storage.task_store import TaskStore
        ts  = TaskStore()
        now = datetime.now(timezone.utc)
        fired: list[str] = []

        for task in ts.load():
            if task.status in ("paused", "running", "failed", "done"):
                continue
            if not task.recurring:
                if task.status != "queued":
                    continue
                if _queue_locked(task, now):
                    continue
                scheduled_for = _parse_datetime(task.scheduled_for)
                next_attempt_at = _parse_datetime(task.next_attempt_at)
                due_scheduled = bool(scheduled_for and now >= scheduled_for)
                due_retry = bool(next_attempt_at and now >= next_attempt_at)
                due_immediate = not task.scheduled_for and not task.next_attempt_at
                if not due_immediate and not due_scheduled and not due_retry:
                    continue
                handler = self._handlers.get(task.id)
                if handler is None:
                    continue
                ts.update(task.id, {
                    "status": "running",
                    "locked_at": now.isoformat(),
                    "locked_by": "scheduler",
                    "last_error": "",
                })
                try:
                    handler()
                    updated = ts.update(task.id, {
                        "scheduled_for": "",
                        "next_attempt_at": "",
                        "locked_at": "",
                        "locked_by": "",
                        "attempts": 0,
                        "last_run": now.isoformat(),
                        "last_error": "",
                    })
                    if updated is not None and updated.status == "running":
                        ts.update(task.id, {"status": "done"})
                    fired.append(task.id)
                except TaskRunCancelled as exc:
                    ts.update(task.id, {
                        "locked_at": "",
                        "locked_by": "",
                    })
                    ts.add_event(task.id, {
                        "kind": "interrupted",
                        "runner": "scheduler",
                        "reason": str(exc or "task cancelled")[:300],
                    })
                except Exception as exc:
                    _mark_queue_failure(ts, task, str(exc), now=now)
                continue
            if not task.cadence:
                continue

            # initialize next_run_at on first encounter
            if not task.next_run_at:
                nxt = next_run_from_cadence(task.cadence)
                ts.update(task.id, {"next_run_at": nxt.isoformat()})
                continue

            try:
                next_run = _parse_datetime(task.next_run_at)
                if next_run is None:
                    raise ValueError("invalid datetime")
            except (ValueError, TypeError):
                nxt = next_run_from_cadence(task.cadence)
                ts.update(task.id, {"next_run_at": nxt.isoformat()})
                continue

            if now < next_run:
                continue

            handler = self._handlers.get(task.id)
            if handler is None:
                continue

            nxt = _advance(next_run, task.cadence)
            ts.update(task.id, {
                "next_run_at": nxt.isoformat(),
                "last_run":    now.isoformat(),
                "last_error":  "",
                "status":      "running",
            })
            fired.append(task.id)
            try:
                handler()
                ts.update(task.id, {"status": "queued"})
            except Exception as exc:
                ts.update(task.id, {"status": "queued", "last_error": str(exc)[:300]})

        return fired

    def run_forever(self) -> None:
        """Boucle de polling. À lancer dans un thread daemon."""
        while not self._stop.wait(self._poll):
            try:
                self.tick()
            except Exception:
                pass

    def stop(self) -> None:
        self._stop.set()


# ── helpers publics ───────────────────────────────────────────────────────────


def cadence_to_seconds(cadence: str) -> int | None:
    """Convertit une cadence en secondes, None = manuel/non planifié."""
    raw = (cadence or "manual").strip().lower().replace(" ", "")
    aliases = {
        "manual":   None,
        "off":      None,
        "disabled": None,
        "hourly":   3600,
        "weekly":   7 * 86400,
    }
    if raw in aliases:
        return aliases[raw]
    unit   = raw[-1:] if raw else ""
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


def next_run_for_time(hhmm: str) -> datetime:
    """Prochain datetime UTC pour une heure HH:MM en heure locale machine."""
    h, m = _parse_hhmm(hhmm)
    now_local = datetime.now().astimezone()
    candidate = now_local.replace(hour=h, minute=m, second=0, microsecond=0)
    if candidate <= now_local:
        candidate += timedelta(days=1)
    return candidate.astimezone(timezone.utc)


def next_run_from_cadence(cadence: str, after: datetime | None = None) -> datetime:
    """Calcule le prochain datetime d'exécution depuis une cadence."""
    now = after or datetime.now(timezone.utc)
    cadence = (cadence or "").strip()

    # HH:MM -> every day at a specific local time
    if re.match(r"^\d{1,2}:\d{2}$", cadence):
        return next_run_for_time(cadence)

    secs = cadence_to_seconds(cadence)
    if secs is None:
        return now + timedelta(days=365)   # manual = very far future
    return now + timedelta(seconds=secs)


def validate_hhmm(hhmm: str) -> str:
    """Valide et normalise une heure HH:MM. Lève ValueError si invalide."""
    h, m = _parse_hhmm(hhmm)
    return f"{h:02d}:{m:02d}"


# ── helpers privés ────────────────────────────────────────────────────────────


def _parse_hhmm(hhmm: str) -> tuple[int, int]:
    raw = hhmm.strip().replace("h", ":")
    try:
        parts = raw.split(":")
        h, m = int(parts[0]), int(parts[1])
    except (ValueError, IndexError, AttributeError):
        raise ValueError(f"Format d'heure invalide : {hhmm!r}")
    if not (0 <= h <= 23 and 0 <= m <= 59):
        raise ValueError(f"Heure hors limites : {hhmm!r}")
    return h, m


def _parse_datetime(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat((value or "").replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def _queue_locked(task: Any, now: datetime) -> bool:
    locked_at = _parse_datetime(getattr(task, "locked_at", ""))
    return bool(locked_at and now - locked_at < timedelta(minutes=5))


def _retry_delay_seconds(attempts: int) -> int:
    return min(300, 10 * (2 ** max(0, attempts - 1)))


def _mark_queue_failure(ts: Any, task: Any, error: str, *, now: datetime) -> None:
    attempts = int(getattr(task, "attempts", 0) or 0) + 1
    max_attempts = max(1, int(getattr(task, "max_attempts", 5) or 5))
    short_error = str(error or "send_failed")[:300]
    if attempts >= max_attempts:
        ts.update(task.id, {
            "status": "failed",
            "attempts": attempts,
            "last_error": short_error,
            "scheduled_for": "",
            "next_attempt_at": "",
            "locked_at": "",
            "locked_by": "",
        })
        ts.add_event(task.id, {
            "kind": "launch_failed",
            "runner": "scheduler",
            "attempts": attempts,
            "error": short_error,
        })
        return

    retry_at = now + timedelta(seconds=_retry_delay_seconds(attempts))
    ts.update(task.id, {
        "status": "queued",
        "attempts": attempts,
        "last_error": short_error,
        "scheduled_for": "",
        "next_attempt_at": retry_at.isoformat(),
        "locked_at": "",
        "locked_by": "",
    })
    ts.add_event(task.id, {
        "kind": "retry_scheduled",
        "runner": "scheduler",
        "attempts": attempts,
        "next_attempt_at": retry_at.isoformat(),
        "error": short_error,
    })


def _advance(last: datetime, cadence: str) -> datetime:
    """Calcule le prochain slot sans accumulation de retard."""
    now  = datetime.now(timezone.utc)

    # HH:MM -> every day at that local time, starting tomorrow
    if re.match(r"^\d{1,2}:\d{2}$", cadence.strip()):
        return next_run_for_time(cadence)

    secs = cadence_to_seconds(cadence)
    if secs is None:
        return now + timedelta(days=365)

    nxt = last + timedelta(seconds=secs)
    while nxt <= now:
        nxt += timedelta(seconds=secs)
    return nxt
