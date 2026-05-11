"""Tests du scheduler de jobs périodiques."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import pytest

from marius.kernel.scheduler import (
    JobStore, Scheduler, ScheduledJob,
    cadence_to_seconds, ensure_jobs, ensure_watch_jobs, next_run_for_time, validate_hhmm, _advance_daily,
)


# ── JobStore ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path: Path) -> JobStore:
    return JobStore(tmp_path / "jobs.json")


def _future(minutes: int = 60) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()


def _past(minutes: int = 5) -> str:
    return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).isoformat()


def test_store_empty_on_init(store: JobStore) -> None:
    assert store.load() == []


def test_store_upsert_and_load(store: JobStore) -> None:
    job = ScheduledJob(id="j1", name="dreaming", run_at=_future(), interval_seconds=86400)
    store.upsert(job)
    loaded = store.load()
    assert len(loaded) == 1
    assert loaded[0].id == "j1"


def test_store_upsert_replaces_existing(store: JobStore) -> None:
    store.upsert(ScheduledJob(id="j1", name="dreaming", run_at=_future(), interval_seconds=86400))
    store.upsert(ScheduledJob(id="j1", name="dreaming", run_at=_future(120), interval_seconds=86400))
    assert len(store.load()) == 1


def test_store_due_returns_past_jobs(store: JobStore) -> None:
    store.upsert(ScheduledJob(id="past",   name="dreaming", run_at=_past(),   interval_seconds=86400))
    store.upsert(ScheduledJob(id="future", name="daily",    run_at=_future(), interval_seconds=86400))
    due = store.due()
    assert len(due) == 1
    assert due[0].id == "past"


def test_store_due_skips_running(store: JobStore) -> None:
    job = ScheduledJob(id="j1", name="dreaming", run_at=_past(), interval_seconds=86400, status="running")
    store.upsert(job)
    assert store.due() == []


def test_store_update(store: JobStore) -> None:
    store.upsert(ScheduledJob(id="j1", name="dreaming", run_at=_past(), interval_seconds=86400))
    job = store.load()[0]
    updated = ScheduledJob(**{**job.__dict__, "last_run": "2026-05-09T09:00:00+00:00"})
    store.update(updated)
    assert store.load()[0].last_run == "2026-05-09T09:00:00+00:00"


def test_store_persists_to_disk(tmp_path: Path) -> None:
    store1 = JobStore(tmp_path / "jobs.json")
    store1.upsert(ScheduledJob(id="j1", name="dreaming", run_at=_future(), interval_seconds=86400))
    store2 = JobStore(tmp_path / "jobs.json")
    assert len(store2.load()) == 1


# ── Scheduler ─────────────────────────────────────────────────────────────────


def test_scheduler_runs_due_job(store: JobStore) -> None:
    store.upsert(ScheduledJob(id="j1", name="dreaming", run_at=_past(), interval_seconds=86400))
    fired = []
    sched = Scheduler(store, {"dreaming": lambda: fired.append(1)})
    sched.tick()
    assert len(fired) == 1


def test_scheduler_skips_future_job(store: JobStore) -> None:
    store.upsert(ScheduledJob(id="j1", name="dreaming", run_at=_future(), interval_seconds=86400))
    fired = []
    sched = Scheduler(store, {"dreaming": lambda: fired.append(1)})
    sched.tick()
    assert fired == []


def test_scheduler_reschedules_after_run(store: JobStore) -> None:
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    store.upsert(ScheduledJob(id="j1", name="dreaming", run_at=past.isoformat(), interval_seconds=86400))
    sched = Scheduler(store, {"dreaming": lambda: None})
    sched.tick()
    job = store.load()[0]
    next_run = datetime.fromisoformat(job.run_at)
    assert next_run > datetime.now(timezone.utc)


def test_scheduler_records_last_run(store: JobStore) -> None:
    store.upsert(ScheduledJob(id="j1", name="dreaming", run_at=_past(), interval_seconds=86400))
    sched = Scheduler(store, {"dreaming": lambda: None})
    sched.tick()
    assert store.load()[0].last_run is not None


def test_scheduler_records_error_but_reschedules(store: JobStore) -> None:
    store.upsert(ScheduledJob(id="j1", name="dreaming", run_at=_past(), interval_seconds=86400))

    def failing():
        raise RuntimeError("provider down")

    sched = Scheduler(store, {"dreaming": failing})
    sched.tick()
    job = store.load()[0]
    assert job.last_error == "provider down"
    assert job.status == "scheduled"
    assert datetime.fromisoformat(job.run_at) > datetime.now(timezone.utc)


def test_scheduler_ignores_unknown_handler(store: JobStore) -> None:
    store.upsert(ScheduledJob(id="j1", name="unknown_job", run_at=_past(), interval_seconds=86400))
    sched = Scheduler(store, {})
    sched.tick()  # ne doit pas lever


def test_scheduler_calls_before_tick(store: JobStore) -> None:
    calls = []
    store.upsert(ScheduledJob(id="j1", name="dreaming", run_at=_past(), interval_seconds=86400))
    sched = Scheduler(store, {"dreaming": lambda: None}, before_tick=lambda: calls.append(1))

    sched.tick()

    assert calls == [1]


# ── ensure_jobs ───────────────────────────────────────────────────────────────


def test_ensure_jobs_creates_both(store: JobStore) -> None:
    ensure_jobs(store, dream_time="02:00", daily_time="08:00")
    names = {j.name for j in store.list_all()}
    assert "dreaming" in names
    assert "daily" in names


def test_ensure_jobs_idempotent(store: JobStore) -> None:
    ensure_jobs(store, dream_time="02:00", daily_time="08:00")
    ensure_jobs(store, dream_time="02:00", daily_time="08:00")
    assert len(store.list_all()) == 2


def test_ensure_jobs_skips_empty_time(store: JobStore) -> None:
    ensure_jobs(store, dream_time="", daily_time="08:00")
    names = {j.name for j in store.list_all()}
    assert "dreaming" not in names
    assert "daily" in names


def test_cadence_to_seconds() -> None:
    assert cadence_to_seconds("manual") is None
    assert cadence_to_seconds("hourly") == 3600
    assert cadence_to_seconds("daily") == 86400
    assert cadence_to_seconds("15m") == 900
    assert cadence_to_seconds("2h") == 7200
    assert cadence_to_seconds("3d") == 259200


def test_ensure_watch_jobs_creates_and_removes(store: JobStore) -> None:
    from types import SimpleNamespace

    ensure_watch_jobs(store, [
        SimpleNamespace(id="topic-a", cadence="hourly", enabled=True),
        SimpleNamespace(id="topic-b", cadence="manual", enabled=True),
    ])
    jobs = store.list_all()
    assert {job.id for job in jobs} == {"watch:topic-a"}
    assert jobs[0].interval_seconds == 3600

    ensure_watch_jobs(store, [SimpleNamespace(id="topic-a", cadence="manual", enabled=True)])
    assert store.list_all() == []


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


def test_advance_daily_no_accumulation() -> None:
    old = datetime.now(timezone.utc) - timedelta(days=3)
    result = _advance_daily(old, 86400)
    assert result > datetime.now(timezone.utc)
    assert result < datetime.now(timezone.utc) + timedelta(days=2)
