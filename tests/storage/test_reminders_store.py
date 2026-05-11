"""Tests du store de rappels planifiés et du parseur d'expressions temporelles."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from marius.storage.reminders_store import RemindersStore, parse_remind_at


# ── fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path: Path) -> RemindersStore:
    return RemindersStore(tmp_path / "reminders.json")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── RemindersStore.add ────────────────────────────────────────────────────────


def test_add_returns_reminder_with_id(store: RemindersStore) -> None:
    remind_at = _now() + timedelta(minutes=10)
    r = store.add("Appeler le médecin", remind_at)
    assert r.id
    assert r.text == "Appeler le médecin"
    assert r.fired is False


def test_add_persists_to_disk(store: RemindersStore, tmp_path: Path) -> None:
    remind_at = _now() + timedelta(hours=1)
    store.add("Faire la vaisselle", remind_at)
    reloaded = RemindersStore(tmp_path / "reminders.json")
    assert len(reloaded.load()) == 1


def test_add_stores_utc(store: RemindersStore) -> None:
    remind_at = _now() + timedelta(minutes=5)
    r = store.add("Test UTC", remind_at)
    stored = datetime.fromisoformat(r.remind_at)
    assert stored.tzinfo is not None


def test_add_with_chat_id(store: RemindersStore) -> None:
    remind_at = _now() + timedelta(minutes=5)
    r = store.add("Message Telegram", remind_at, chat_id=42)
    assert r.chat_id == 42


# ── RemindersStore.due ────────────────────────────────────────────────────────


def test_due_returns_past_reminders(store: RemindersStore) -> None:
    past = _now() - timedelta(seconds=1)
    store.add("À livrer", past)
    assert len(store.due()) == 1


def test_due_excludes_future_reminders(store: RemindersStore) -> None:
    future = _now() + timedelta(hours=1)
    store.add("Pas encore", future)
    assert store.due() == []


def test_due_excludes_already_fired(store: RemindersStore) -> None:
    past = _now() - timedelta(seconds=1)
    r = store.add("Déjà livré", past)
    store.mark_fired(r.id)
    assert store.due() == []


def test_due_accepts_custom_now(store: RemindersStore) -> None:
    t = _now() + timedelta(hours=2)
    store.add("Dans 2h", t)
    future_now = _now() + timedelta(hours=3)
    assert len(store.due(now=future_now)) == 1


# ── RemindersStore.mark_fired ─────────────────────────────────────────────────


def test_mark_fired_sets_flag(store: RemindersStore) -> None:
    r = store.add("Test", _now() - timedelta(seconds=1))
    store.mark_fired(r.id)
    reminders = store.load()
    assert reminders[0].fired is True
    assert reminders[0].fired_at is not None


def test_mark_fired_unknown_id_is_noop(store: RemindersStore) -> None:
    store.mark_fired("inexistant")   # ne lève pas


# ── RemindersStore.list_pending ───────────────────────────────────────────────


def test_list_pending_excludes_fired(store: RemindersStore) -> None:
    r1 = store.add("Actif", _now() + timedelta(hours=1))
    r2 = store.add("Tiré", _now() - timedelta(seconds=1))
    store.mark_fired(r2.id)
    pending = store.list_pending()
    assert len(pending) == 1
    assert pending[0].id == r1.id


def test_cancel_removes_pending_reminder(store: RemindersStore) -> None:
    reminder = store.add("À annuler", _now() + timedelta(hours=1))

    assert store.cancel(reminder.id) is True
    assert store.list_pending() == []


def test_cancel_keeps_fired_reminder(store: RemindersStore) -> None:
    reminder = store.add("Déjà livré", _now() - timedelta(seconds=1))
    store.mark_fired(reminder.id)

    assert store.cancel(reminder.id) is False
    assert store.load()[0].id == reminder.id


# ── parse_remind_at ───────────────────────────────────────────────────────────


def test_parse_relative_minutes() -> None:
    before = _now()
    result = parse_remind_at("20m")
    assert abs((result - before).total_seconds() - 1200) < 2


def test_parse_relative_hours() -> None:
    before = _now()
    result = parse_remind_at("2h")
    assert abs((result - before).total_seconds() - 7200) < 2


def test_parse_relative_days() -> None:
    before = _now()
    result = parse_remind_at("1d")
    assert abs((result - before).total_seconds() - 86400) < 2


def test_parse_compact_hour_hhmm() -> None:
    result = parse_remind_at("14h30")
    assert result.tzinfo is not None
    local = result.astimezone()
    assert local.hour == 14
    assert local.minute == 30


def test_parse_colon_time() -> None:
    result = parse_remind_at("08:00")
    assert result.tzinfo is not None
    local = result.astimezone()
    assert local.hour == 8
    assert local.minute == 0


def test_parse_iso_datetime() -> None:
    future = (_now() + timedelta(hours=5)).replace(second=0, microsecond=0)
    # isoformat() inclut le tzinfo (+00:00) — parse_remind_at le respecte
    result = parse_remind_at(future.isoformat())
    assert abs((result - future).total_seconds()) < 2


def test_parse_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_remind_at("demain matin")


def test_parse_next_day_if_time_passed() -> None:
    # Une heure très tôt le matin, très probablement passée
    result = parse_remind_at("00:01")
    local = result.astimezone()
    now_local = datetime.now().astimezone()
    assert result > _now()
    # Doit être soit aujourd'hui (si pas encore passé) soit demain
    delta = (result - _now()).total_seconds()
    assert 0 < delta <= 86400 + 60
