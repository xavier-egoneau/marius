from __future__ import annotations

from pathlib import Path

import pytest

from marius.storage.project_store import ProjectEntry, ProjectStore


@pytest.fixture()
def store(tmp_path: Path) -> ProjectStore:
    return ProjectStore(store_path=tmp_path / "projects.json")


# ── record_open ───────────────────────────────────────────────────────────────


def test_record_open_creates_entry(store: ProjectStore, tmp_path: Path) -> None:
    project = tmp_path / "myproject"
    project.mkdir()
    entry = store.record_open(project)
    assert entry.name == "myproject"
    assert entry.session_count == 1


def test_record_open_increments_session_count(store: ProjectStore, tmp_path: Path) -> None:
    project = tmp_path / "myproject"
    project.mkdir()
    store.record_open(project)
    entry = store.record_open(project)
    assert entry.session_count == 2


def test_record_open_updates_last_opened(store: ProjectStore, tmp_path: Path) -> None:
    project = tmp_path / "myproject"
    project.mkdir()
    first = store.record_open(project)
    second = store.record_open(project)
    assert second.last_opened >= first.last_opened


def test_record_open_resolves_path(store: ProjectStore, tmp_path: Path) -> None:
    project = tmp_path / "myproject"
    project.mkdir()
    store.record_open(project)
    entry = store.get(project)
    assert entry is not None
    assert Path(entry.path) == project.resolve()


# ── load ──────────────────────────────────────────────────────────────────────


def test_load_empty_store(store: ProjectStore) -> None:
    assert store.load() == []


def test_load_returns_entries(store: ProjectStore, tmp_path: Path) -> None:
    for name in ("alpha", "beta", "gamma"):
        p = tmp_path / name
        p.mkdir()
        store.record_open(p)
    entries = store.load()
    assert len(entries) == 3


def test_load_sorted_by_last_opened_desc(store: ProjectStore, tmp_path: Path) -> None:
    for name in ("alpha", "beta"):
        p = tmp_path / name
        p.mkdir()
        store.record_open(p)
    entries = store.load()
    assert entries[0].last_opened >= entries[1].last_opened


# ── get ───────────────────────────────────────────────────────────────────────


def test_get_known_project(store: ProjectStore, tmp_path: Path) -> None:
    project = tmp_path / "myproject"
    project.mkdir()
    store.record_open(project)
    result = store.get(project)
    assert result is not None
    assert result.name == "myproject"


def test_get_unknown_project_returns_none(store: ProjectStore, tmp_path: Path) -> None:
    project = tmp_path / "unknown"
    assert store.get(project) is None


# ── persistance ───────────────────────────────────────────────────────────────


def test_data_persists_across_instances(tmp_path: Path) -> None:
    store_path = tmp_path / "projects.json"
    project = tmp_path / "myproject"
    project.mkdir()

    store1 = ProjectStore(store_path=store_path)
    store1.record_open(project)

    store2 = ProjectStore(store_path=store_path)
    result = store2.get(project)
    assert result is not None
    assert result.session_count == 1


def test_corrupt_json_loads_empty(tmp_path: Path) -> None:
    store_path = tmp_path / "projects.json"
    store_path.write_text("not valid json", encoding="utf-8")
    store = ProjectStore(store_path=store_path)
    assert store.load() == []
