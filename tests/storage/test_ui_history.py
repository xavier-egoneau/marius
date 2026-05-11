from __future__ import annotations

from pathlib import Path

from marius.storage.ui_history import (
    FileVisibleConversationStore,
    InMemoryVisibleHistoryStore,
    VisibleHistoryEntry,
)


def test_visible_history_store_preserves_order_per_session() -> None:
    store = InMemoryVisibleHistoryStore()
    store.append(
        "canon",
        VisibleHistoryEntry(role="user", content="Bonjour"),
    )
    store.append(
        "canon",
        VisibleHistoryEntry(role="assistant", content="Salut"),
    )

    entries = store.list_entries("canon")

    assert [entry.content for entry in entries] == ["Bonjour", "Salut"]


def test_visible_history_store_is_isolated_between_sessions() -> None:
    store = InMemoryVisibleHistoryStore()
    store.append("canon", VisibleHistoryEntry(role="user", content="A"))
    store.append("branch-1", VisibleHistoryEntry(role="user", content="B"))

    assert [entry.content for entry in store.list_entries("canon")] == ["A"]
    assert [entry.content for entry in store.list_entries("branch-1")] == ["B"]


def test_visible_history_store_returns_copies_to_avoid_accidental_mutation() -> None:
    store = InMemoryVisibleHistoryStore()
    store.append(
        "canon",
        VisibleHistoryEntry(
            role="assistant",
            content="Diff prêt",
            artifacts=[{"type": "diff", "path": "changes.diff"}],
        ),
    )

    entries = store.list_entries("canon")
    entries[0].content = "mutated"

    fresh_entries = store.list_entries("canon")
    assert fresh_entries[0].content == "Diff prêt"


def test_visible_history_store_deep_copies_nested_metadata_and_artifacts() -> None:
    store = InMemoryVisibleHistoryStore()
    store.append(
        "canon",
        VisibleHistoryEntry(
            role="assistant",
            content="Nested payload",
            metadata={"nested": {"count": 1}},
            artifacts=[{"type": "report", "payload": {"ok": True}}],
        ),
    )

    entries = store.list_entries("canon")
    entries[0].metadata["nested"]["count"] = 99
    entries[0].artifacts[0]["payload"]["ok"] = False

    fresh_entries = store.list_entries("canon")
    assert fresh_entries[0].metadata["nested"]["count"] == 1
    assert fresh_entries[0].artifacts[0]["payload"]["ok"] is True


def test_file_visible_conversation_store_archives_and_lists(tmp_path: Path) -> None:
    store = FileVisibleConversationStore(tmp_path)

    summary = store.archive(
        [
            {"role": "user", "content": "Premier sujet"},
            {"role": "assistant", "content": "Réponse"},
        ],
        agent="main",
        opened_at="2026-05-11T10:00:00+00:00",
        closed_at="2026-05-11T10:05:00+00:00",
    )

    assert summary is not None
    assert summary["title"] == "Premier sujet"
    assert summary["turns"] == 1
    assert store.list()[0]["id"] == summary["id"]


def test_file_visible_conversation_store_loads_messages(tmp_path: Path) -> None:
    store = FileVisibleConversationStore(tmp_path)
    summary = store.archive(
        [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
        agent="main",
    )

    assert summary is not None
    record = store.load(summary["id"])

    assert record is not None
    assert [msg["content"] for msg in record["messages"]] == ["Hello", "Hi"]


def test_file_visible_conversation_store_ignores_empty_archives(tmp_path: Path) -> None:
    store = FileVisibleConversationStore(tmp_path)

    assert store.archive([], agent="main") is None
    assert store.archive([{"role": "tool", "content": "hidden"}], agent="main") is None
    assert store.list() == []
