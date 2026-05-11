from __future__ import annotations

from datetime import datetime, timedelta, timezone

from marius.storage.reminders_store import RemindersStore
from marius.tools.reminders import make_reminders_tool


def _store(tmp_path) -> RemindersStore:
    return RemindersStore(tmp_path / "reminders.json")


def test_reminders_tool_create_is_default_action(tmp_path):
    tool = make_reminders_tool(_store(tmp_path))

    result = tool.handler({"text": "Boire de l'eau", "remind_at": "20m"})

    assert result.ok is True
    assert result.data["reminder_id"]


def test_reminders_tool_lists_pending_reminders(tmp_path):
    store = _store(tmp_path)
    reminder = store.add("Appeler", datetime.now(timezone.utc) + timedelta(hours=1))
    tool = make_reminders_tool(store)

    result = tool.handler({"action": "list"})

    assert result.ok is True
    assert result.data["reminders"][0]["reminder_id"] == reminder.id
    assert "Appeler" in result.summary


def test_reminders_tool_cancel_removes_pending_reminder(tmp_path):
    store = _store(tmp_path)
    reminder = store.add("Annuler moi", datetime.now(timezone.utc) + timedelta(hours=1))
    tool = make_reminders_tool(store)

    result = tool.handler({"action": "cancel", "reminder_id": reminder.id})

    assert result.ok is True
    assert store.list_pending() == []


def test_reminders_tool_cancel_unknown_id_returns_error(tmp_path):
    tool = make_reminders_tool(_store(tmp_path))

    result = tool.handler({"action": "cancel", "reminder_id": "missing"})

    assert result.ok is False
    assert result.error == "reminder_not_found"
