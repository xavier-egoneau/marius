from __future__ import annotations

from marius.storage import task_store as task_store_module
from marius.storage.task_store import TaskStore
from marius.tools.tasks import make_task_tools


def test_task_update_ignores_blank_board_metadata_and_description(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    task = TaskStore().create({
        "title": "Initial title",
        "status": "queued",
        "priority": "high",
        "agent": "main",
        "project_path": "/tmp/project",
        "prompt": "old",
    })

    result = make_task_tools()["task_update"].handler({
        "id": task.id,
        "title": "",
        "status": "",
        "priority": "",
        "agent": "",
        "project_path": "",
        "description": "ignored",
        "prompt": "new",
    })

    assert result.ok is True
    updated = TaskStore().load()[0]
    assert updated.title == "Initial title"
    assert updated.status == "queued"
    assert updated.priority == "high"
    assert updated.agent == "main"
    assert updated.project_path == "/tmp/project"
    assert updated.prompt == "new"


def test_task_create_ignores_description_field(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)

    result = make_task_tools()["task_create"].handler({
        "title": "Create me",
        "description": "ignored",
    })

    assert result.ok is True
    task = TaskStore().load()[0]
    assert task.prompt == ""


def test_task_store_maps_legacy_review_to_done(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    TaskStore().create({"title": "Legacy review", "status": "review"})

    task = TaskStore().load()[0]

    assert task.status == "done"


def test_task_update_allows_failure_reason(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    task = TaskStore().create({"title": "Initial title", "status": "running"})

    result = make_task_tools()["task_update"].handler({
        "id": task.id,
        "status": "failed",
        "last_error": "permission refused",
    })

    assert result.ok is True
    updated = TaskStore().load()[0]
    assert updated.status == "failed"
    assert updated.last_error == "permission refused"


def test_recover_interrupted_running_tasks_for_agent(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    store = TaskStore()
    interrupted = store.create({"title": "Interrupted", "status": "running", "agent": "main"})
    store.create({"title": "Other agent", "status": "running", "agent": "codeur"})
    store.create({"title": "Already queued", "status": "queued", "agent": "main"})

    recovered = store.recover_interrupted_running("main", reason="gateway restart")

    tasks = {task.title: task for task in store.load()}
    assert [task.id for task in recovered] == [interrupted.id]
    assert tasks["Interrupted"].status == "queued"
    assert tasks["Interrupted"].last_error == "gateway restart"
    assert tasks["Other agent"].status == "running"
    assert tasks["Already queued"].status == "queued"
    assert any(event["kind"] == "interrupted" for event in tasks["Interrupted"].events)
