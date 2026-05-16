from __future__ import annotations

from pathlib import Path

from marius.tools.allow_roots import make_allow_root_tools


def test_allow_root_add_list_and_remove(tmp_path: Path) -> None:
    tools = make_allow_root_tools(store_path=tmp_path / "allowed_roots.json")
    project = tmp_path / "project"
    project.mkdir()

    added = tools["allow_root_add"].handler({"path": str(project), "reason": "test"})
    listed = tools["allow_root_list"].handler({})
    removed = tools["allow_root_remove"].handler({"path": str(project)})
    listed_after = tools["allow_root_list"].handler({})

    assert added.ok is True
    assert added.data["allowed_root"]["path"] == str(project.resolve())
    assert listed.ok is True
    assert listed.data["allowed_roots"] == [added.data["allowed_root"]]
    assert removed.ok is True
    assert listed_after.data["allowed_roots"] == []


def test_allow_root_add_requires_path(tmp_path: Path) -> None:
    tools = make_allow_root_tools(store_path=tmp_path / "allowed_roots.json")

    result = tools["allow_root_add"].handler({})

    assert result.ok is False
    assert result.error == "missing_path"


def test_allow_root_remove_reports_missing_path(tmp_path: Path) -> None:
    tools = make_allow_root_tools(store_path=tmp_path / "allowed_roots.json")

    result = tools["allow_root_remove"].handler({"path": str(tmp_path / "missing")})

    assert result.ok is False
    assert result.error == "allow_root_not_found"
