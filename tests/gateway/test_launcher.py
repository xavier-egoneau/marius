from __future__ import annotations

import os
import signal
import sys
from types import SimpleNamespace

from marius.gateway import launcher


def test_stop_sends_sigterm_and_waits_for_socket_removal(monkeypatch, tmp_path):
    pid_file = tmp_path / "main.pid"
    socket_file = tmp_path / "main.sock"
    pid_file.write_text("1234", encoding="utf-8")
    socket_file.touch()
    killed = []

    monkeypatch.setattr(launcher, "pid_path", lambda _agent: pid_file)
    monkeypatch.setattr(launcher, "socket_path", lambda _agent: socket_file)

    def fake_kill(pid, sig):
        killed.append((pid, sig))
        socket_file.unlink()

    monkeypatch.setattr(os, "kill", fake_kill)

    assert launcher.stop("main") is True
    assert killed == [(1234, signal.SIGTERM)]


def test_stop_returns_false_without_pid(monkeypatch, tmp_path):
    monkeypatch.setattr(launcher, "pid_path", lambda _agent: tmp_path / "missing.pid")

    assert launcher.stop("main") is False


def test_start_prefers_enabled_systemd_service(monkeypatch, tmp_path):
    calls: list[str] = []
    socket_file = tmp_path / "main.sock"
    ping_results = iter([False, True])

    service = SimpleNamespace(
        is_systemd_available=lambda: True,
        is_service_installed=lambda: True,
        agent_active_state=lambda _agent: "inactive",
        agent_enabled_state=lambda _agent: "enabled",
        start_agent=lambda agent: calls.append(agent) or (True, ""),
    )

    monkeypatch.setitem(sys.modules, "marius.gateway.service", service)
    monkeypatch.setattr(launcher, "socket_path", lambda _agent: socket_file)
    monkeypatch.setattr(launcher, "_ping", lambda _agent: next(ping_results))

    assert launcher.start("main") is True
    assert calls == ["main"]
