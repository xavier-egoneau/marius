"""Canal web Marius — HTTP + SSE, stdlib uniquement.

Architecture :
  - ThreadingHTTPServer : une connexion = un thread
  - POST /api/message   : démarre le tour dans un thread, retourne immédiatement
  - GET  /api/stream    : SSE — vide la queue de la session en cours
  - DELETE /api/session : réinitialise la conversation

Le gateway est passé par injection. Aucune référence inverse.
"""

from __future__ import annotations

import json
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

_DEFAULT_PORT = 8765
_SSE_KEEPALIVE = 25  # secondes entre deux keep-alive


class SessionProgressStore:
    """Queue par session pour la diffusion SSE. Thread-safe."""

    def __init__(self) -> None:
        self._queues: dict[str, queue.Queue] = {}
        self._lock = threading.Lock()

    def open(self, session_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=1000)
        with self._lock:
            self._queues[session_id] = q
        return q

    def push(self, session_id: str, event: dict) -> None:
        with self._lock:
            q = self._queues.get(session_id)
        if q is not None:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    def close(self, session_id: str) -> None:
        with self._lock:
            q = self._queues.pop(session_id, None)
        if q is not None:
            q.put(None)   # sentinel → SSE envoie {"done": true}

    def get(self, session_id: str) -> queue.Queue | None:
        with self._lock:
            return self._queues.get(session_id)


class WebServer:
    """Serveur HTTP web intégré au gateway. Démarre dans un thread daemon."""

    def __init__(self, gateway: Any, *, host: str = "127.0.0.1", port: int = _DEFAULT_PORT) -> None:
        self._gw = gateway
        self.host = host
        self.port = port
        self._progress = SessionProgressStore()
        self._httpd: ThreadingHTTPServer | None = None

    def start(self) -> None:
        from marius.storage.log_store import log_event
        handler = _make_handler(self._gw, self._progress)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        t = threading.Thread(
            target=self._httpd.serve_forever,
            daemon=True,
            name="web-server",
        )
        t.start()
        log_event("web_start", {"agent": self._gw.agent_name, "host": self.host, "port": self.port})

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


# ── handler ───────────────────────────────────────────────────────────────────


def _make_handler(gw: Any, progress: SessionProgressStore):
    class Handler(BaseHTTPRequestHandler):

        # ── GET ───────────────────────────────────────────────────────────────

        def do_GET(self) -> None:
            parsed = urlparse(self.path)

            if parsed.path == "/":
                self._html(_ui_html())
                return

            if parsed.path == "/health":
                self._json({
                    "ok": True,
                    "agent": gw.agent_name,
                    "model": gw.entry.model,
                    "provider": gw.entry.name,
                })
                return

            if parsed.path == "/api/stream":
                query = parse_qs(parsed.query)
                session_id = query.get("session_id", ["default"])[0]
                self._sse(progress, session_id)
                return

            if parsed.path == "/api/status":
                turns = len(gw.session.state.turns)
                self._json({"ok": True, "turns": turns, "agent": gw.agent_name})
                return

            self._json({"ok": False, "error": "not_found"}, 404)

        # ── POST ──────────────────────────────────────────────────────────────

        def do_POST(self) -> None:
            parsed = urlparse(self.path)

            if parsed.path == "/api/message":
                try:
                    payload = self._read_json()
                    text = str(payload.get("text") or payload.get("message") or "").strip()
                    session_id = str(payload.get("session_id") or "default")
                except Exception as exc:
                    self._json({"ok": False, "error": str(exc)}, 400)
                    return
                if not text:
                    self._json({"ok": False, "error": "empty_message"}, 400)
                    return
                _start_turn(gw, progress, text, session_id)
                self._json({"ok": True, "session_id": session_id, "pending": True})
                return

            self._json({"ok": False, "error": "not_found"}, 404)

        # ── DELETE ────────────────────────────────────────────────────────────

        def do_DELETE(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/session":
                gw.new_conversation()
                self._json({"ok": True})
                return
            self._json({"ok": False, "error": "not_found"}, 404)

        # ── SSE ───────────────────────────────────────────────────────────────

        def _sse(self, store: SessionProgressStore, session_id: str) -> None:
            import queue as _q

            q = store.get(session_id)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()

            if q is None:
                self.wfile.write(b'data: {"done":true,"reason":"no_active_run"}\n\n')
                self.wfile.flush()
                return

            try:
                while True:
                    try:
                        event = q.get(timeout=_SSE_KEEPALIVE)
                    except _q.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        continue
                    if event is None:
                        self.wfile.write(b'data: {"done":true}\n\n')
                        self.wfile.flush()
                        break
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass

        # ── helpers ───────────────────────────────────────────────────────────

        def _read_json(self) -> dict:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

        def _json(self, payload: dict, status: int = 200) -> None:
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _html(self, html: str) -> None:
            body = html.encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: Any) -> None:
            pass

    return Handler


# ── exécution du tour ─────────────────────────────────────────────────────────


def _start_turn(gw: Any, progress: SessionProgressStore, text: str, session_id: str) -> None:
    """Lance le tour LLM dans un thread daemon, pousse les événements dans la queue SSE."""
    progress.open(session_id)

    def _run() -> None:
        try:
            gw.run_turn_for_web(text, lambda event: progress.push(session_id, event))
        except Exception as exc:
            progress.push(session_id, {"type": "error", "error": str(exc)})
        finally:
            progress.close(session_id)

    threading.Thread(target=_run, daemon=True, name=f"web-turn-{session_id[:8]}").start()


# ── UI HTML ───────────────────────────────────────────────────────────────────

import functools

@functools.cache
def _ui_html() -> str:
    path = Path(__file__).parent / "ui.html"
    if path.exists():
        return path.read_text(encoding="utf-8")
    return _FALLBACK_HTML


_FALLBACK_HTML = """<!DOCTYPE html>
<html><head><meta charset="UTF-8"><title>Marius</title></head>
<body><p>ui.html manquant.</p></body></html>"""
