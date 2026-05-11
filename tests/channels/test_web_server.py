from __future__ import annotations

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
