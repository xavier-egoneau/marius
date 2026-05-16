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


def test_task_update_ignores_blank_prompt(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    task = TaskStore().create({
        "title": "Initial title",
        "status": "backlog",
        "prompt": "keep this plan",
    })

    result = make_task_tools()["task_update"].handler({
        "id": task.id,
        "status": "queued",
        "prompt": "",
    })

    assert result.ok is True
    updated = TaskStore().load()[0]
    assert updated.status == "queued"
    assert updated.prompt == "keep this plan"


def test_task_create_ignores_description_field(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)

    result = make_task_tools()["task_create"].handler({
        "title": "Create me",
        "description": "ignored",
    })

    assert result.ok is True
    task = TaskStore().load()[0]
    assert task.prompt == ""


def test_task_create_defaults_to_current_agent(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)

    result = make_task_tools(default_agent="main")["task_create"].handler({
        "title": "Create project folder",
    })

    assert result.ok is True
    task = TaskStore().load()[0]
    assert task.agent == "main"


def test_task_create_new_project_defaults_to_queued_and_current_agent(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)

    result = make_task_tools(default_agent="main")["task_create"].handler({
        "title": "Créer projet toto",
        "project_path": "nouveau",
    })

    assert result.ok is True
    task = TaskStore().load()[0]
    assert task.status == "queued"
    assert task.agent == "main"
    assert task.project_path == "nouveau"


def test_task_create_explicit_agent_overrides_default(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)

    result = make_task_tools(default_agent="main")["task_create"].handler({
        "title": "Worker task",
        "agent": "codeur",
    })

    assert result.ok is True
    task = TaskStore().load()[0]
    assert task.agent == "codeur"


def test_task_create_routine_requires_supported_cadence(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)

    result = make_task_tools()["task_create"].handler({
        "title": "Daily",
        "recurring": True,
        "cadence": "daily",
    })

    assert result.ok is False
    assert result.error == "invalid_cadence"
    assert TaskStore().load() == []


def test_task_create_routine_normalizes_time_cadence_and_defaults_queued(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)

    result = make_task_tools()["task_create"].handler({
        "title": "Daily",
        "recurring": True,
        "cadence": "9h30",
    })

    assert result.ok is True
    task = TaskStore().load()[0]
    assert task.status == "queued"
    assert task.cadence == "09:30"
    assert task.scheduled_for == ""


def test_task_create_scheduled_unique_task_defaults_queued_and_validates_iso(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)

    invalid = make_task_tools()["task_create"].handler({
        "title": "Later",
        "scheduled_for": "tomorrow at ten",
    })
    valid = make_task_tools()["task_create"].handler({
        "title": "Later",
        "scheduled_for": "2026-05-15T10:00:00+02:00",
    })

    assert invalid.ok is False
    assert invalid.error == "invalid_scheduled_for"
    assert valid.ok is True
    task = TaskStore().load()[0]
    assert task.status == "queued"


def test_task_list_defaults_to_unique_tasks(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    TaskStore().create({"title": "Unique"})
    TaskStore().create({"title": "Routine", "recurring": True, "cadence": "1d"})

    result = make_task_tools()["task_list"].handler({})

    assert result.ok is True
    assert [task["title"] for task in result.data["tasks"]] == ["Unique"]


def test_task_list_can_filter_routines(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    TaskStore().create({"title": "Unique"})
    TaskStore().create({"title": "Routine", "recurring": True, "cadence": "1d"})

    result = make_task_tools()["task_list"].handler({"recurring": True})

    assert result.ok is True
    assert [task["title"] for task in result.data["tasks"]] == ["Routine"]


def test_task_store_maps_legacy_review_to_done(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    TaskStore().create({"title": "Legacy review", "status": "review"})

    task = TaskStore().load()[0]

    assert task.status == "done"


def test_task_store_maps_legacy_archived_to_done(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    TaskStore().create({"title": "Legacy archive", "status": "archived"})

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


def test_task_update_running_to_backlog_requests_cancel_and_clears_lock(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    task = TaskStore().create({
        "title": "Running task",
        "status": "running",
        "locked_at": "2026-05-15T23:18:48+00:00",
        "locked_by": "scheduler",
    })

    result = make_task_tools()["task_update"].handler({
        "id": task.id,
        "status": "backlog",
    })

    assert result.ok is True
    updated = TaskStore().load()[0]
    assert updated.status == "backlog"
    assert updated.locked_at == ""
    assert updated.locked_by == ""
    assert any(event["kind"] == "cancel_requested" for event in updated.events)


def test_recover_interrupted_running_tasks_for_agent(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    store = TaskStore()
    interrupted = store.create({"title": "Interrupted", "status": "running", "agent": "main"})
    routine = store.create({"title": "Routine", "status": "running", "agent": "main", "recurring": True})
    store.create({"title": "Other agent", "status": "running", "agent": "codeur"})
    store.create({"title": "Already queued", "status": "queued", "agent": "main"})

    recovered = store.recover_interrupted_running("main", reason="gateway restart")

    tasks = {task.title: task for task in store.load()}
    assert [task.id for task in recovered] == [interrupted.id, routine.id]
    assert tasks["Interrupted"].status == "failed"
    assert tasks["Interrupted"].last_error == "gateway restart"
    assert tasks["Routine"].status == "queued"
    assert tasks["Other agent"].status == "running"
    assert tasks["Already queued"].status == "queued"
    assert any(event["kind"] == "interrupted" for event in tasks["Interrupted"].events)
