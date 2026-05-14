"""Tests du scheduler de tâches récurrentes."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from marius.kernel.scheduler import (
    TaskScheduler,
    cadence_to_seconds, next_run_for_time, validate_hhmm,
)
from marius.storage.task_store import TaskStore
from marius.storage import task_store as task_store_module


# ── cadence_to_seconds ────────────────────────────────────────────────────────


def test_cadence_to_seconds() -> None:
    assert cadence_to_seconds("manual") is None
    assert cadence_to_seconds("hourly") == 3600
    assert cadence_to_seconds("daily") == 86400
    assert cadence_to_seconds("15m") == 900
    assert cadence_to_seconds("2h") == 7200
    assert cadence_to_seconds("3d") == 259200


# ── helpers ───────────────────────────────────────────────────────────────────


def test_next_run_future() -> None:
    dt = next_run_for_time("23:59")
    assert dt > datetime.now(timezone.utc)
    assert dt.tzinfo is not None   # toujours UTC aware


def test_next_run_always_utc_aware() -> None:
    dt = next_run_for_time("02:00")
    assert dt.tzinfo is not None
    assert dt.utcoffset().total_seconds() == 0   # UTC


def test_next_run_interprets_local_time() -> None:
    # L'heure retournée doit correspondre à HH:MM dans le tz local
    h, m = 3, 0
    dt = next_run_for_time("03:00")
    local = dt.astimezone()           # reconvertir en local
    # L'heure locale doit être 03:00 (aujourd'hui ou demain)
    assert local.hour == h and local.minute == m


def test_validate_hhmm_valid() -> None:
    assert validate_hhmm("09:00") == "09:00"
    assert validate_hhmm("9:00")  == "09:00"
    assert validate_hhmm("9h30")  == "09:30"
    assert validate_hhmm("23:59") == "23:59"


def test_validate_hhmm_invalid() -> None:
    import pytest as _pytest
    with _pytest.raises(ValueError):
        validate_hhmm("25:00")
    with _pytest.raises(ValueError):
        validate_hhmm("09:60")
    with _pytest.raises(ValueError):
        validate_hhmm("not-a-time")
    with _pytest.raises(ValueError):
        validate_hhmm("")


def test_scheduler_runs_due_one_shot_task(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    task = TaskStore().create({
        "title": "Run once",
        "status": "queued",
        "agent": "main",
        "scheduled_for": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    })
    fired: list[str] = []
    scheduler = TaskScheduler({task.id: lambda: fired.append(task.id)})

    assert scheduler.tick() == [task.id]
    updated = TaskStore().load()[0]
    assert fired == [task.id]
    assert updated.status == "running"
    assert updated.scheduled_for == ""


def test_scheduler_ignores_queued_one_shot_without_schedule(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    task = TaskStore().create({
        "title": "Run now",
        "status": "queued",
        "agent": "main",
    })
    fired: list[str] = []
    scheduler = TaskScheduler({task.id: lambda: fired.append(task.id)})

    assert scheduler.tick() == []
    updated = TaskStore().load()[0]
    assert fired == []
    assert updated.status == "queued"


def test_scheduler_ignores_backlog_one_shot_task(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    task = TaskStore().create({
        "title": "Idea",
        "status": "backlog",
        "agent": "main",
        "scheduled_for": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat(),
    })
    scheduler = TaskScheduler({task.id: lambda: None})

    assert scheduler.tick() == []
    assert TaskStore().load()[0].status == "backlog"


def test_scheduler_retries_failed_one_shot_send(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    due = datetime.now(timezone.utc) - timedelta(minutes=1)
    task = TaskStore().create({
        "title": "Run once",
        "status": "queued",
        "agent": "main",
        "scheduled_for": due.isoformat(),
    })
    scheduler = TaskScheduler({task.id: lambda: (_ for _ in ()).throw(OSError("busy"))})

    assert scheduler.tick() == []
    updated = TaskStore().load()[0]
    assert updated.status == "queued"
    assert updated.attempts == 1
    assert updated.next_attempt_at
    assert updated.locked_at == ""
    assert updated.last_error == "busy"
