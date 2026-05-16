from __future__ import annotations

from pathlib import Path

from marius.storage.allow_root_store import AllowRootStore


def test_add_persists_allowed_root(tmp_path: Path) -> None:
    store_path = tmp_path / "allowed_roots.json"
    project = tmp_path / "project"
    project.mkdir()

    store = AllowRootStore(store_path)
    added = store.add(project, reason="activate_project")

    assert Path(added.path) == project.resolve()
    assert AllowRootStore(store_path).paths() == (project.resolve(),)


def test_add_is_idempotent(tmp_path: Path) -> None:
    store = AllowRootStore(tmp_path / "allowed_roots.json")
    project = tmp_path / "project"
    project.mkdir()

    first = store.add(project, reason="activate_project")
    second = store.add(project, reason="activate_project")

    assert first == second
    assert store.paths() == (project.resolve(),)


def test_remove_persists_allowed_root_removal(tmp_path: Path) -> None:
    store_path = tmp_path / "allowed_roots.json"
    store = AllowRootStore(store_path)
    project = tmp_path / "project"
    other = tmp_path / "other"
    project.mkdir()
    other.mkdir()
    store.add(project, reason="activate_project")
    store.add(other, reason="activate_project")

    assert store.remove(project) is True

    assert AllowRootStore(store_path).paths() == (other.resolve(),)


def test_remove_missing_allowed_root_returns_false(tmp_path: Path) -> None:
    store = AllowRootStore(tmp_path / "allowed_roots.json")

    assert store.remove(tmp_path / "missing") is False


def test_corrupt_json_loads_empty(tmp_path: Path) -> None:
    store_path = tmp_path / "allowed_roots.json"
    store_path.write_text("{nope", encoding="utf-8")

    assert AllowRootStore(store_path).list() == []
