from __future__ import annotations

import json
from pathlib import Path

from marius.channels.dashboard import server as dashboard_server
from marius.storage import allow_root_store as allow_root_store_module
from marius.storage.allow_root_store import AllowRootStore
from marius.storage.task_store import Task


def test_api_projects_includes_active_project_when_missing_from_recent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / ".marius"
    home.mkdir()
    recent = tmp_path / "recent"
    active = tmp_path / "active"

    (home / "projects.json").write_text(
        json.dumps([
            {
                "path": str(recent),
                "name": "recent",
                "last_opened": "2026-05-10T10:00:00+00:00",
                "session_count": 2,
            }
        ]),
        encoding="utf-8",
    )
    (home / "active_project.json").write_text(
        json.dumps({
            "path": str(active),
            "name": "active",
            "set_at": "2026-05-14T10:00:00+00:00",
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(dashboard_server, "_MARIUS_HOME", home)

    data = dashboard_server._api_projects()

    assert data["active_path"] == str(active)
    assert data["projects"][0]["path"] == str(active)
    assert data["projects"][0]["active"] is True
    assert {p["path"] for p in data["projects"]} == {str(active), str(recent)}


def test_api_projects_patch_set_active_records_existing_unknown_project(
    monkeypatch,
    tmp_path: Path,
) -> None:
    home = tmp_path / ".marius"
    home.mkdir()
    project = tmp_path / "project"
    project.mkdir()
    monkeypatch.setattr(dashboard_server, "_MARIUS_HOME", home)

    ok, message = dashboard_server._api_projects_patch({
        "path": str(project),
        "set_active": True,
    })

    assert ok is True
    assert message == "updated"
    active = json.loads((home / "active_project.json").read_text(encoding="utf-8"))
    projects = json.loads((home / "projects.json").read_text(encoding="utf-8"))
    assert active["path"] == str(project.resolve())
    assert projects[0]["path"] == str(project.resolve())


def test_task_payloads_mark_running_agents(monkeypatch) -> None:
    calls: list[str] = []

    def fake_is_running(name: str) -> bool:
        calls.append(name)
        return name == "main"

    monkeypatch.setattr(dashboard_server, "_is_running", fake_is_running)
    monkeypatch.setattr(dashboard_server, "_pending_permissions_by_agent", lambda _names: {})
    tasks = [
        Task(id="t1", title="A", agent="main"),
        Task(id="t2", title="B", agent="offline"),
        Task(id="t3", title="C", agent="main"),
    ]

    rows = dashboard_server._task_payloads(tasks)

    assert [r["running_agent"] for r in rows] == [True, False, True]
    assert calls == ["main", "offline"]


def test_task_payloads_mark_pending_permission(monkeypatch) -> None:
    monkeypatch.setattr(dashboard_server, "_is_running", lambda _name: True)
    monkeypatch.setattr(
        dashboard_server,
        "_pending_permissions_by_agent",
        lambda _names: {
            "main": [{
                "request_id": "p1",
                "tool": "make_dir",
                "reason": "Écriture hors du projet",
                "created_at": "2026-05-14T10:00:00+00:00",
            }]
        },
    )

    rows = dashboard_server._task_payloads([
        Task(id="t1", title="A", agent="main", status="running"),
        Task(id="t2", title="B", agent="main", status="queued"),
    ])

    assert rows[0]["permission_pending"] is True
    assert rows[0]["permission_reason"] == "Écriture hors du projet"
    assert rows[1]["permission_pending"] is False


def test_api_allow_roots_add_passes_through_guardian(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / ".marius"
    workspace = tmp_path / "workspace"
    root = tmp_path / "secondBrain" / "todos"
    monkeypatch.setattr(allow_root_store_module, "_MARIUS_HOME", home)
    monkeypatch.setattr(dashboard_server, "_WORKSPACE_ROOT", workspace)

    ok, message = dashboard_server._api_allow_roots_add({
        "path": str(root),
        "reason": "test",
    })

    assert ok is True
    assert message == f"Dossier autorisé : {root.resolve(strict=False)}"
    assert AllowRootStore().paths() == (root.resolve(strict=False),)


def test_api_allow_roots_add_rejects_broad_root(monkeypatch, tmp_path: Path) -> None:
    home = tmp_path / ".marius"
    workspace = tmp_path / "workspace"
    monkeypatch.setattr(allow_root_store_module, "_MARIUS_HOME", home)
    monkeypatch.setattr(dashboard_server, "_WORKSPACE_ROOT", workspace)

    ok, message = dashboard_server._api_allow_roots_add({"path": "/"})

    assert ok is False
    assert "Racine refusée par le gardien" in message
    assert AllowRootStore().paths() == ()
