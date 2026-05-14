from __future__ import annotations

from pathlib import Path

from marius.storage.allow_root_store import AllowRootStore
from marius.tools.projects import make_project_tools


def test_project_list_reports_active_and_known_projects(tmp_path: Path) -> None:
    project = tmp_path / "alpha"
    project.mkdir()
    tools = make_project_tools(
        store_path=tmp_path / "projects.json",
        active_path=tmp_path / "active_project.json",
    )
    tools["project_set_active"].handler({"path": str(project)})

    result = tools["project_list"].handler({})

    assert result.ok is True
    assert result.data["active_project"]["name"] == "alpha"
    assert result.data["projects"][0]["name"] == "alpha"
    assert "Active project" in result.summary


def test_project_set_active_accepts_known_project_name(tmp_path: Path) -> None:
    project = tmp_path / "alpha"
    project.mkdir()
    tools = make_project_tools(
        store_path=tmp_path / "projects.json",
        active_path=tmp_path / "active_project.json",
    )
    tools["project_set_active"].handler({"path": str(project)})
    beta = tmp_path / "beta"
    beta.mkdir()
    tools["project_set_active"].handler({"path": str(beta)})

    result = tools["project_set_active"].handler({"name": "alpha"})

    assert result.ok is True
    assert result.data["active_project"]["name"] == "alpha"


def test_project_set_active_rejects_missing_path(tmp_path: Path) -> None:
    tools = make_project_tools(
        store_path=tmp_path / "projects.json",
        active_path=tmp_path / "active_project.json",
    )

    result = tools["project_set_active"].handler({"path": str(tmp_path / "missing")})

    assert result.ok is False
    assert result.error == "project_path_missing"


def test_project_set_active_can_create_missing_path(tmp_path: Path) -> None:
    project = tmp_path / "alpha"
    tools = make_project_tools(
        store_path=tmp_path / "projects.json",
        active_path=tmp_path / "active_project.json",
        allow_store_path=tmp_path / "allowed_roots.json",
    )

    result = tools["project_set_active"].handler({"path": str(project), "create": True})

    assert result.ok is True
    assert project.is_dir()
    assert result.data["active_project"]["path"] == str(project.resolve())
    assert AllowRootStore(tmp_path / "allowed_roots.json").paths() == (project.resolve(),)


def test_project_set_active_rejects_unknown_name(tmp_path: Path) -> None:
    tools = make_project_tools(
        store_path=tmp_path / "projects.json",
        active_path=tmp_path / "active_project.json",
    )

    result = tools["project_set_active"].handler({"name": "missing"})

    assert result.ok is False
    assert result.error == "project_not_found"


def test_project_set_active_resolves_relative_path_from_cwd(tmp_path: Path) -> None:
    project = tmp_path / "alpha"
    project.mkdir()
    tools = make_project_tools(
        cwd=tmp_path,
        store_path=tmp_path / "projects.json",
        active_path=tmp_path / "active_project.json",
    )

    result = tools["project_set_active"].handler({"path": "alpha"})

    assert result.ok is True
    assert result.data["active_project"]["path"] == str(project.resolve())
