from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from marius.storage.memory_store import MemoryStore


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    s = MemoryStore(db_path=tmp_path / "memory.db")
    yield s
    s.close()


# ── add ───────────────────────────────────────────────────────────────────────


def test_add_returns_memory_id(store: MemoryStore) -> None:
    memory_id = store.add("J'aime le café le matin")
    assert isinstance(memory_id, int)
    assert memory_id > 0


def test_add_deduplicates_by_content(store: MemoryStore) -> None:
    id1 = store.add("contenu identique")
    id2 = store.add("contenu identique")
    assert id1 == id2


def test_add_strips_whitespace(store: MemoryStore) -> None:
    id1 = store.add("  même contenu  ")
    id2 = store.add("même contenu")
    assert id1 == id2


def test_add_empty_content_raises(store: MemoryStore) -> None:
    with pytest.raises(ValueError):
        store.add("")


def test_add_with_category_and_tags(store: MemoryStore) -> None:
    memory_id = store.add("Python est mon langage préféré", category="préférences", tags="tech,langages")
    entries = store.list()
    assert any(e.id == memory_id and e.category == "préférences" and e.tags == "tech,langages" for e in entries)


# ── remove ────────────────────────────────────────────────────────────────────


def test_remove_existing_entry(store: MemoryStore) -> None:
    memory_id = store.add("à supprimer")
    assert store.remove(memory_id) is True


def test_remove_nonexistent_entry_returns_false(store: MemoryStore) -> None:
    assert store.remove(99999) is False


def test_remove_makes_entry_disappear(store: MemoryStore) -> None:
    memory_id = store.add("temporaire")
    store.remove(memory_id)
    entries = store.list()
    assert all(e.id != memory_id for e in entries)


# ── replace ───────────────────────────────────────────────────────────────────


def test_replace_existing_entry(store: MemoryStore) -> None:
    store.add("ancienne préférence")

    assert store.replace("ancienne", "nouvelle préférence") is True

    entries = store.list()
    assert entries[0].content == "nouvelle préférence"


def test_replace_nonexistent_entry_returns_false(store: MemoryStore) -> None:
    store.add("souvenir présent")

    assert store.replace("absent", "nouveau souvenir") is False


# ── list ──────────────────────────────────────────────────────────────────────


def test_list_returns_entries(store: MemoryStore) -> None:
    store.add("premier souvenir")
    store.add("deuxième souvenir")
    entries = store.list()
    assert len(entries) == 2


def test_list_empty_store(store: MemoryStore) -> None:
    assert store.list() == []


def test_list_filter_by_category(store: MemoryStore) -> None:
    store.add("souvenir A", category="perso")
    store.add("souvenir B", category="pro")
    perso = store.list(category="perso")
    assert len(perso) == 1
    assert perso[0].category == "perso"


def test_list_respects_limit(store: MemoryStore) -> None:
    for i in range(10):
        store.add(f"souvenir numéro {i}")
    entries = store.list(limit=3)
    assert len(entries) == 3


def test_list_orders_by_most_recent(store: MemoryStore) -> None:
    store.add("premier")
    store.add("deuxième")
    entries = store.list()
    assert entries[0].content == "deuxième"


# ── search ────────────────────────────────────────────────────────────────────


def test_search_finds_matching_content(store: MemoryStore) -> None:
    store.add("J'utilise pytest pour les tests")
    results = store.search("pytest")
    assert len(results) == 1
    assert "pytest" in results[0].content


def test_search_empty_query_returns_empty(store: MemoryStore) -> None:
    store.add("quelque chose")
    assert store.search("") == []


def test_search_no_match_returns_empty(store: MemoryStore) -> None:
    store.add("Python")
    assert store.search("Rust") == []


def test_search_filter_by_category(store: MemoryStore) -> None:
    store.add("café matinal", category="habitudes")
    store.add("café au bureau", category="travail")
    results = store.search("café", category="habitudes")
    assert len(results) == 1
    assert results[0].category == "habitudes"


def test_search_respects_limit(store: MemoryStore) -> None:
    for i in range(5):
        store.add(f"Python project numéro {i}")
    results = store.search("Python", limit=2)
    assert len(results) <= 2


def test_search_also_matches_tags(store: MemoryStore) -> None:
    store.add("mon outil favori", tags="python,cli")
    results = store.search("cli")
    assert len(results) == 1


# ── context manager ───────────────────────────────────────────────────────────


def test_context_manager_closes_cleanly(tmp_path: Path) -> None:
    with MemoryStore(db_path=tmp_path / "cm.db") as s:
        s.add("test context manager")


# ── migrations ────────────────────────────────────────────────────────────────


def test_migrates_pre_scope_database(tmp_path: Path) -> None:
    db_path = tmp_path / "old-memory.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(
        """
        CREATE TABLE memories (
            memory_id  INTEGER PRIMARY KEY AUTOINCREMENT,
            content    TEXT NOT NULL UNIQUE,
            category   TEXT NOT NULL DEFAULT 'general',
            tags       TEXT NOT NULL DEFAULT '',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO memories (content, category, tags)
            VALUES ('ancien souvenir pytest', 'general', 'tests');
        """
    )
    conn.close()

    store = MemoryStore(db_path=db_path)
    try:
        entries = store.list()
        assert len(entries) == 1
        assert entries[0].content == "ancien souvenir pytest"
        assert entries[0].scope == "global"
        assert entries[0].project_path is None
        assert store.search("pytest")[0].content == "ancien souvenir pytest"
    finally:
        store.close()
