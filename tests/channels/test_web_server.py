from __future__ import annotations

import json
import threading

from marius.channels.web.server import WebServer


class _Socket:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.closed = False
        self.sent: list[bytes] = []

    def sendall(self, payload: bytes) -> None:
        if self.fail:
            raise BrokenPipeError("stale gateway socket")
        self.sent.append(payload)

    def close(self) -> None:
        self.closed = True


def _web_server(sock: _Socket) -> WebServer:
    ws = WebServer.__new__(WebServer)
    ws.agent_name = "main"
    ws.port = 8765
    ws._sock = sock
    ws._send_lock = threading.Lock()
    ws._connect_lock = threading.Lock()
    ws._buf = bytearray()
    ws._active_session = None
    ws._current_assistant = ""
    ws._history = []
    ws._sse_queues = {}
    ws._queues_lock = threading.Lock()
    ws._pending_perms = {}
    ws._perms_lock = threading.Lock()
    ws._save_history = lambda: None
    return ws


def test_send_input_reconnects_once_after_stale_gateway_socket() -> None:
    stale = _Socket(fail=True)
    fresh = _Socket()
    ws = _web_server(stale)
    ws.connect = lambda: setattr(ws, "_sock", fresh)

    ws.send_input("salut", "main")

    assert stale.closed is True
    assert len(fresh.sent) == 1
    assert b'"type": "input"' in fresh.sent[0]
    assert ws._history == [{"role": "user", "content": "salut", "created_at": ws._history[0]["created_at"]}]


def test_send_input_reports_gateway_failure_without_persisting_user_message() -> None:
    stale = _Socket(fail=True)
    ws = _web_server(stale)

    def fail_connect() -> None:
        raise FileNotFoundError("gateway missing")

    ws.connect = fail_connect

    try:
        ws.send_input("salut", "main")
    except OSError:
        pass
    else:
        raise AssertionError("send_input should fail when the gateway cannot be reached")

    assert ws._history == []
    assert ws._active_session is None


def test_open_sse_replays_pending_permissions() -> None:
    ws = _web_server(_Socket())
    ev = threading.Event()
    ws._pending_perms["abc123"] = {
        "event": ev,
        "result": [False],
        "tool": "make_dir",
        "reason": "Écriture hors du projet",
        "session_id": "default",
        "created_at": "2026-05-14T10:00:00+00:00",
    }

    q = ws.open_sse("web-new")
    replay = q.get_nowait()

    assert replay == {
        "type": "permission_request",
        "tool": "make_dir",
        "reason": "Écriture hors du projet",
        "request_id": "abc123",
    }
    assert ws.pending_permissions()[0]["request_id"] == "abc123"


def test_permission_request_broadcasts_to_open_chat_sessions(monkeypatch) -> None:
    from marius.channels.web import server as web_server_module

    monkeypatch.setattr(web_server_module, "_PERMISSION_TIMEOUT_SECONDS", 0.05)
    ws = _web_server(_Socket())
    ws._active_session = "default"
    default_q = ws.open_sse("default")
    chat_q = ws.open_sse("web-open")

    t = threading.Thread(
        target=ws._dispatch,
        args=(json.dumps({
            "type": "permission_request",
            "request_id": "p1",
            "tool_name": "make_dir",
            "reason": "Écriture hors du projet",
        }),),
    )
    t.start()
    first = default_q.get(timeout=1)
    second = chat_q.get(timeout=1)
    ws.approve_permission("p1", True)
    t.join(timeout=1)

    assert first["request_id"] == "p1"
    assert second["request_id"] == "p1"
    assert first["type"] == second["type"] == "permission_request"
