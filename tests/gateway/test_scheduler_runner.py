from __future__ import annotations

import socket
import threading

from marius.gateway.protocol import DoneEvent, WelcomeEvent, decode, encode
from marius.gateway import scheduler_runner as scheduler_runner_module
from marius.gateway.scheduler_runner import GatewayScheduler
from marius.gateway import workspace as workspace_module
from marius.storage import task_store as task_store_module
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
