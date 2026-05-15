from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

from marius.channels.dashboard import server as dashboard_server
from marius.storage import allow_root_store as allow_root_store_module
from marius.storage import project_store as project_store_module
from marius.storage import task_store as task_store_module
from marius.storage.allow_root_store import AllowRootStore
from marius.storage.project_store import ProjectStore
from marius.storage.task_store import TaskStore


def test_launch_task_runs_immediate_backlog_task(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        dashboard_server,
        "_send_to_agent",
        lambda agent, message: sent.append((agent, message)) or {"ok": True},
    )
    task = TaskStore().create({
        "title": "Do it",
        "prompt": "Implémente le truc",
        "status": "backlog",
        "agent": "main",
    })

    status, payload = dashboard_server._launch_task(TaskStore(), task.id)

    assert status == 200
    assert payload["ok"] is True
    assert payload["scheduled"] is False
    assert len(sent) == 1
    assert sent[0][0] == "main"
    assert "Task id:" in sent[0][1]
    assert f"id={task.id}" in sent[0][1]
    assert 'status="done"' in sent[0][1]
    assert "Implémente le truc" in sent[0][1]
    updated = TaskStore().load()[0]
    assert updated.status == "running"
    assert [e["to"] for e in updated.events if e["kind"] == "status_changed"][-2:] == ["queued", "running"]


def test_launch_task_preserves_explicit_slash_command(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        dashboard_server,
        "_send_to_agent",
        lambda agent, message: sent.append((agent, message)) or {"ok": True},
    )
    task = TaskStore().create({
        "title": "Do it",
        "prompt": "/dev Implémente le truc",
        "status": "backlog",
        "agent": "main",
    })

    dashboard_server._launch_task(TaskStore(), task.id)

    assert len(sent) == 1
    assert sent[0][1].startswith("/dev ")
    assert "Implémente le truc" in sent[0][1]
    assert f"id={task.id}" in sent[0][1]


def test_launch_task_schedules_future_task_without_sending(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    monkeypatch.setattr(
        dashboard_server,
        "_send_to_agent",
        lambda _agent, _message: (_ for _ in ()).throw(AssertionError("should not send")),
    )
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    task = TaskStore().create({
        "title": "Later",
        "status": "backlog",
        "agent": "main",
        "scheduled_for": future.isoformat(),
    })

    status, payload = dashboard_server._launch_task(TaskStore(), task.id)

    assert status == 200
    assert payload["ok"] is True
    assert payload["scheduled"] is True
    updated = TaskStore().load()[0]
    assert updated.status == "queued"
    assert updated.scheduled_for == future.isoformat()


def test_launch_task_keeps_queued_and_schedules_retry_on_send_failure(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    monkeypatch.setattr(
        dashboard_server,
        "_send_to_agent",
        lambda _agent, _message: {"ok": False, "error": "[Errno 11] Resource temporarily unavailable"},
    )
    task = TaskStore().create({
        "title": "Do it",
        "prompt": "Implémente le truc",
        "status": "backlog",
        "agent": "main",
    })

    status, payload = dashboard_server._launch_task(TaskStore(), task.id)

    assert status == 200
    assert payload["ok"] is True
    assert payload["retry_scheduled"] is True
    updated = TaskStore().load()[0]
    assert updated.status == "queued"
    assert updated.attempts == 1
    assert updated.next_attempt_at
    assert "Resource temporarily unavailable" in updated.last_error


def test_launch_recurring_task_uses_routine_channel(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    sent: list[tuple[str, str]] = []
    done = threading.Event()

    def fake_send(agent: str, prompt: str) -> dict:
        sent.append((agent, prompt))
        done.set()
        return {"ok": True}

    monkeypatch.setattr(dashboard_server, "_send_routine_to_agent", fake_send)
    monkeypatch.setattr(
        dashboard_server,
        "_send_to_agent",
        lambda _agent, _message: (_ for _ in ()).throw(AssertionError("should not use task channel")),
    )
    task = TaskStore().create({
        "title": "Ping",
        "prompt": "envois moi un ping",
        "status": "queued",
        "agent": "main",
        "recurring": True,
        "cadence": "02:30",
    })

    status, payload = dashboard_server._launch_task(TaskStore(), task.id)

    assert status == 202
    assert payload["ok"] is True
    assert payload["routine"] is True
    assert done.wait(1.0)
    assert sent == [("main", "envois moi un ping")]
    deadline = time.monotonic() + 1.0
    while True:
        updated = TaskStore().load()[0]
        if any(event.get("kind") == "launched" for event in updated.events):
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(0.01)
    assert updated.status == "queued"
    assert updated.last_error == ""
    assert any(
        event.get("kind") == "launched"
        and event.get("channel") == "routine"
        and event.get("manual") is True
        for event in updated.events
    )


def test_launch_task_prepares_new_project_marker(monkeypatch, tmp_path) -> None:
    marius_home = tmp_path / ".marius"
    projects_root = tmp_path / "Documents" / "projets"
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", marius_home)
    monkeypatch.setattr(project_store_module, "_MARIUS_HOME", marius_home)
    monkeypatch.setattr(allow_root_store_module, "_MARIUS_HOME", marius_home)
    monkeypatch.setattr(dashboard_server, "_DEFAULT_PROJECTS_ROOT", projects_root)
    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        dashboard_server,
        "_send_to_agent",
        lambda agent, message: sent.append((agent, message)) or {"ok": True},
    )
    task = TaskStore().create({
        "title": "Créer un nouveau dossier test2",
        "status": "backlog",
        "agent": "main",
        "project_path": "nouveau",
    })

    status, payload = dashboard_server._launch_task(TaskStore(), task.id)

    project_path = projects_root / "test2"
    assert status == 200
    assert payload["ok"] is True
    assert project_path.is_dir()
    assert ProjectStore().get(project_path) is not None
    assert [root.path for root in AllowRootStore().list()] == [str(project_path.resolve())]
    updated = TaskStore().load()[0]
    assert updated.project_path == str(project_path.resolve())
    assert any(event["kind"] == "new_project_prepared" for event in updated.events)
    assert f"Projet cible: {project_path.resolve()}" in sent[0][1]
    assert 'status="done"' in sent[0][1]


def test_launch_task_new_project_marker_requires_name(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    monkeypatch.setattr(dashboard_server, "_DEFAULT_PROJECTS_ROOT", tmp_path / "projects")
    monkeypatch.setattr(
        dashboard_server,
        "_send_to_agent",
        lambda _agent, _message: (_ for _ in ()).throw(AssertionError("should not send")),
    )
    task = TaskStore().create({
        "title": "Créer un nouveau projet",
        "status": "backlog",
        "agent": "main",
        "project_path": "nouveau",
    })

    status, payload = dashboard_server._launch_task(TaskStore(), task.id)

    assert status == 400
    assert payload["ok"] is False
    assert "no project name" in payload["error"]

