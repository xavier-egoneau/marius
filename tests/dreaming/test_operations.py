"""Tests des opérations dreaming (parse + apply)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from marius.dreaming.operations import DreamingResult, apply_operations, parse_response
from marius.storage.memory_store import MemoryStore


# ── parse_response ────────────────────────────────────────────────────────────


def test_parse_empty_response() -> None:
    ops, summary = parse_response("")
    assert ops == []
    assert summary == ""


def test_parse_valid_json() -> None:
    data = {
        "operations": [
            {"op": "add", "content": "Fait A", "scope": "global", "tags": ""},
        ],
        "summary": "1 ajouté.",
    }
    ops, summary = parse_response(json.dumps(data))
    assert len(ops) == 1
    assert ops[0]["op"] == "add"
    assert summary == "1 ajouté."


def test_parse_json_with_preamble() -> None:
    response = 'Voici les opérations :\n\n' + json.dumps({
        "operations": [{"op": "remove", "text": "vieux fait"}],
        "summary": "1 supprimé.",
    })
    ops, summary = parse_response(response)
    assert len(ops) == 1
    assert ops[0]["op"] == "remove"


def test_parse_no_operations_key() -> None:
    ops, _ = parse_response('{"summary": "rien"}')
    assert ops == []


def test_parse_invalid_json() -> None:
    ops, summary = parse_response("{ invalid json }")
    assert ops == []


# ── apply_operations ──────────────────────────────────────────────────────────


@pytest.fixture()
def store(tmp_path: Path) -> MemoryStore:
    return MemoryStore(tmp_path / "test.db")


def test_apply_add(store: MemoryStore) -> None:
    ops = [{"op": "add", "content": "Nouveau fait", "scope": "global", "tags": ""}]
    result = apply_operations(ops, store)
    assert result.added == 1
    assert result.errors == 0
    entries = store.list()
    assert any("Nouveau fait" in e.content for e in entries)


def test_apply_add_project_scope(store: MemoryStore, tmp_path: Path) -> None:
    ops = [{"op": "add", "content": "Fait projet", "scope": "project", "project_path": str(tmp_path)}]
    result = apply_operations(ops, store)
    assert result.added == 1
    entries = store.list(scope="project")
    assert len(entries) == 1
    assert entries[0].project_path == str(tmp_path)


def test_apply_replace(store: MemoryStore) -> None:
    store.add("Ancien contenu exact")
    ops = [{"op": "replace", "old": "Ancien contenu", "new": "Nouveau contenu mis à jour"}]
    result = apply_operations(ops, store)
    assert result.updated == 1
    entries = store.list()
    assert any("Nouveau contenu mis à jour" in e.content for e in entries)


def test_apply_replace_not_found(store: MemoryStore) -> None:
    ops = [{"op": "replace", "old": "inexistant", "new": "quelque chose"}]
    result = apply_operations(ops, store)
    assert result.updated == 0
    assert result.errors == 1


def test_apply_remove(store: MemoryStore) -> None:
    store.add("Fait à supprimer")
    ops = [{"op": "remove", "text": "à supprimer"}]
    result = apply_operations(ops, store)
    assert result.removed == 1
    entries = store.list()
    assert not any("à supprimer" in e.content for e in entries)


def test_apply_remove_not_found(store: MemoryStore) -> None:
    ops = [{"op": "remove", "text": "inexistant"}]
    result = apply_operations(ops, store)
    assert result.removed == 0
    assert result.errors == 1


def test_apply_unknown_op(store: MemoryStore) -> None:
    ops = [{"op": "unknown", "content": "..."}]
    result = apply_operations(ops, store)
    assert result.errors == 1


def test_apply_add_empty_content(store: MemoryStore) -> None:
    ops = [{"op": "add", "content": "", "scope": "global"}]
    result = apply_operations(ops, store)
    assert result.errors == 1
    assert result.added == 0


def test_apply_mixed_operations(store: MemoryStore) -> None:
    store.add("Fait existant à remplacer")
    store.add("Fait existant à supprimer")
    ops = [
        {"op": "add",     "content": "Nouveau fait", "scope": "global", "tags": ""},
        {"op": "replace", "old": "à remplacer",     "new": "Fait mis à jour"},
        {"op": "remove",  "text": "à supprimer"},
    ]
    result = apply_operations(ops, store)
    assert result.added   == 1
    assert result.updated == 1
    assert result.removed == 1
    assert result.errors  == 0
    assert result.total_ops == 3


def test_dreaming_result_str_with_summary() -> None:
    r = DreamingResult(added=2, updated=1, removed=0, summary="Bilan custom.")
    assert str(r) == "Bilan custom."


def test_dreaming_result_str_no_ops() -> None:
    r = DreamingResult()
    assert "jour" in str(r).lower()


def test_dreaming_result_str_with_ops() -> None:
    r = DreamingResult(added=3, updated=1, removed=2)
    s = str(r)
    assert "3" in s
    assert "1" in s
    assert "2" in s
