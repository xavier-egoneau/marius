from __future__ import annotations

import socket
import threading

from marius.gateway.protocol import DoneEvent, PermissionRequestEvent, WelcomeEvent, decode, encode
from marius.gateway import scheduler_runner as scheduler_runner_module
from marius.gateway.scheduler_runner import GatewayScheduler
from marius.kernel.scheduler import TaskRunCancelled
from marius.gateway import workspace as workspace_module
from marius.storage import task_store as task_store_module
from marius.storage import allow_root_store as allow_root_store_module
from marius.storage.task_store import TaskStore


def test_scheduler_user_task_keeps_socket_open_until_done(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    monkeypatch.setattr(scheduler_runner_module, "log_event", lambda *_args, **_kwargs: None)

    sock_path = tmp_path / "main.sock"
    monkeypatch.setattr(workspace_module, "socket_path", lambda _agent: sock_path)

    task = TaskStore().create({
        "title": "Ping",
        "prompt": "envois moi un ping",
        "status": "queued",
        "agent": "main",
        "recurring": True,
        "cadence": "02:30",
    })

    input_seen = threading.Event()
    listening = threading.Event()
    closed_too_soon = threading.Event()

    def server() -> None:
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)
        listening.set()
        try:
            conn, _ = srv.accept()
            with conn:
                conn.sendall(encode(WelcomeEvent(agent="main", model="test", provider="test")))
                buf = b""
                while b"\n" not in buf:
                    buf += conn.recv(4096)
                raw, _buf = buf.split(b"\n", 1)
                event = decode(raw.decode("utf-8"))
                assert event["type"] == "input"
                assert event["channel"] == "routine"
                assert event["text"] == "envois moi un ping"
                input_seen.set()

                conn.settimeout(0.1)
                try:
                    if conn.recv(1) == b"":
                        closed_too_soon.set()
                except socket.timeout:
                    pass
                conn.sendall(encode(DoneEvent()))
        finally:
            srv.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert listening.wait(1.0)

    runner = object.__new__(GatewayScheduler)
    runner.agent_name = "main"
    runner._run_user_task(task.id)

    assert input_seen.wait(1.0)
    thread.join(1.0)
    assert not closed_too_soon.is_set()


def test_scheduler_one_shot_task_uses_task_board_prompt(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    monkeypatch.setattr(scheduler_runner_module, "log_event", lambda *_args, **_kwargs: None)

    sock_path = tmp_path / "main.sock"
    monkeypatch.setattr(workspace_module, "socket_path", lambda _agent: sock_path)

    task = TaskStore().create({
        "title": "Veille IA",
        "prompt": "fais une veille IA",
        "status": "queued",
        "agent": "main",
    })

    input_seen = threading.Event()
    listening = threading.Event()

    def server() -> None:
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)
        listening.set()
        try:
            conn, _ = srv.accept()
            with conn:
                conn.sendall(encode(WelcomeEvent(agent="main", model="test", provider="test")))
                buf = b""
                while b"\n" not in buf:
                    buf += conn.recv(4096)
                raw, _buf = buf.split(b"\n", 1)
                event = decode(raw.decode("utf-8"))
                assert event["type"] == "input"
                assert event["channel"] == "task"
                assert "[Task Board]" in event["text"]
                assert f"Task id: {task.id}" in event["text"]
                assert "task_update" in event["text"]
                assert "fais une veille IA" in event["text"]
                input_seen.set()
                conn.sendall(encode(DoneEvent()))
        finally:
            srv.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert listening.wait(1.0)

    runner = object.__new__(GatewayScheduler)
    runner.agent_name = "main"
    runner._run_user_task(task.id)

    assert input_seen.wait(1.0)
    thread.join(1.0)


def test_scheduler_one_shot_task_authorizes_task_project_path(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    monkeypatch.setattr(allow_root_store_module, "_MARIUS_HOME", tmp_path)
    monkeypatch.setattr(scheduler_runner_module, "log_event", lambda *_args, **_kwargs: None)

    sock_path = tmp_path / "main.sock"
    monkeypatch.setattr(workspace_module, "socket_path", lambda _agent: sock_path)

    project_path = tmp_path / "projects" / "trade_plugin"
    task = TaskStore().create({
        "title": "Créer projet trade_plugin",
        "prompt": "crée le dossier projet",
        "status": "queued",
        "agent": "main",
        "project_path": str(project_path),
    })

    input_seen = threading.Event()
    listening = threading.Event()

    def server() -> None:
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)
        listening.set()
        try:
            conn, _ = srv.accept()
            with conn:
                conn.sendall(encode(WelcomeEvent(agent="main", model="test", provider="test")))
                buf = b""
                while b"\n" not in buf:
                    buf += conn.recv(4096)
                raw, _buf = buf.split(b"\n", 1)
                event = decode(raw.decode("utf-8"))
                assert event["type"] == "input"
                assert event["channel"] == "task"
                assert str(project_path) in event["text"]
                input_seen.set()
                conn.sendall(encode(DoneEvent()))
        finally:
            srv.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert listening.wait(1.0)

    runner = object.__new__(GatewayScheduler)
    runner.agent_name = "main"
    runner.workspace = tmp_path / "workspace" / "main"
    runner.permission_mode = "limited"
    runner._run_user_task(task.id)

    assert input_seen.wait(1.0)
    thread.join(1.0)
    assert project_path.resolve(strict=False) in allow_root_store_module.AllowRootStore().paths()


def test_scheduler_task_does_not_auto_deny_permission_request(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    monkeypatch.setattr(scheduler_runner_module, "log_event", lambda *_args, **_kwargs: None)

    sock_path = tmp_path / "main.sock"
    monkeypatch.setattr(workspace_module, "socket_path", lambda _agent: sock_path)

    task = TaskStore().create({
        "title": "Needs permission",
        "prompt": "crée un dossier",
        "status": "queued",
        "agent": "main",
    })

    listening = threading.Event()
    auto_denied = threading.Event()

    def server() -> None:
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)
        listening.set()
        try:
            conn, _ = srv.accept()
            with conn:
                conn.sendall(encode(WelcomeEvent(agent="main", model="test", provider="test")))
                buf = b""
                while b"\n" not in buf:
                    buf += conn.recv(4096)
                conn.sendall(encode(PermissionRequestEvent(
                    tool_name="make_dir",
                    reason="Écriture hors du projet",
                    request_id="p1",
                )))
                conn.settimeout(0.2)
                try:
                    data = conn.recv(4096)
                except socket.timeout:
                    data = b""
                if b"permission_response" in data:
                    auto_denied.set()
                conn.sendall(encode(DoneEvent()))
        finally:
            srv.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert listening.wait(1.0)

    runner = object.__new__(GatewayScheduler)
    runner.agent_name = "main"
    runner._run_user_task(task.id)

    thread.join(1.0)
    assert not auto_denied.is_set()


def test_scheduler_user_task_observes_manual_backlog_cancel(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(task_store_module, "_MARIUS_HOME", tmp_path)
    monkeypatch.setattr(scheduler_runner_module, "log_event", lambda *_args, **_kwargs: None)

    sock_path = tmp_path / "main.sock"
    monkeypatch.setattr(workspace_module, "socket_path", lambda _agent: sock_path)

    task = TaskStore().create({
        "title": "Cancel me",
        "prompt": "audit",
        "status": "running",
        "agent": "main",
        "locked_at": "2026-05-15T23:18:48+00:00",
        "locked_by": "scheduler",
    })

    input_seen = threading.Event()
    listening = threading.Event()
    closed_after_cancel = threading.Event()

    def server() -> None:
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sock_path))
        srv.listen(1)
        listening.set()
        try:
            conn, _ = srv.accept()
            with conn:
                conn.sendall(encode(WelcomeEvent(agent="main", model="test", provider="test")))
                buf = b""
                while b"\n" not in buf:
                    buf += conn.recv(4096)
                raw, _buf = buf.split(b"\n", 1)
                event = decode(raw.decode("utf-8"))
                assert event["type"] == "input"
                assert event["channel"] == "task"
                input_seen.set()
                TaskStore().update(task.id, {"status": "backlog"})
                conn.settimeout(2.0)
                if conn.recv(1) == b"":
                    closed_after_cancel.set()
        finally:
            srv.close()

    thread = threading.Thread(target=server, daemon=True)
    thread.start()
    assert listening.wait(1.0)

    runner = object.__new__(GatewayScheduler)
    runner.agent_name = "main"
    try:
        runner._run_user_task(task.id)
    except TaskRunCancelled:
        pass
    else:
        raise AssertionError("expected TaskRunCancelled")

    assert input_seen.wait(1.0)
    thread.join(3.0)
    assert closed_after_cancel.is_set()
