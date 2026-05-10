"""Canal web Marius — proxy HTTP ↔ socket Unix gateway.

Même protocole JSON-lines que le client CLI.
Le web server maintient UNE connexion socket persistante au gateway
(comme le REPL maintient une connexion terminal).

Tous les browser tabs partagent cette connexion et la même session —
cohérent avec l'architecture mono-session du gateway.

Routes :
  GET  /                  → UI chat HTML
  GET  /health            → info agent/modèle
  GET  /api/stream        → SSE (tokens, outils, permissions, done_turn)
  POST /api/message       → envoie InputEvent au gateway
  POST /api/command       → envoie CommandEvent (/new, /stop)
  POST /api/permission    → répond à une PermissionRequestEvent
  POST /api/upload        → sauvegarde un fichier (base64), retourne le path
"""

from __future__ import annotations

import base64
import json
import queue
import socket
import threading
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from marius.gateway.protocol import (
    CommandEvent, InputEvent, PermissionResponseEvent,
    decode, encode,
)
from marius.gateway.workspace import web_history_path

_SSE_KEEPALIVE = 25   # secondes entre deux keep-alive SSE


# ── WebServer ─────────────────────────────────────────────────────────────────


class WebServer:
    """Proxy HTTP ↔ socket Unix gateway. Connexion persistante."""

    def __init__(
        self,
        agent_name: str,
        socket_path: Path,
        *,
        port: int = 8765,
        host: str = "127.0.0.1",
    ) -> None:
        self.agent_name  = agent_name
        self.socket_path = Path(socket_path)
        self.port        = port
        self.host        = host

        # SSE queues : session_id → Queue
        self._sse_queues: dict[str, queue.Queue] = {}
        self._queues_lock = threading.Lock()

        # Permissions en attente : request_id → (Event, [bool])
        self._pending_perms: dict[str, tuple[threading.Event, list[bool]]] = {}
        self._perms_lock = threading.Lock()

        # Socket gateway
        self._sock: socket.socket | None = None
        self._send_lock = threading.Lock()
        self._buf = bytearray()

        # Session active (tab qui a envoyé le dernier message)
        self._active_session: str | None = None

        # Historique de la conversation (persisté sur disque)
        self._history_path = web_history_path(agent_name)
        self._history: list[dict] = self._load_history()
        self._current_assistant: str = ""       # accumule les deltas du tour en cours

        self._welcome: dict = {}   # données du WelcomeEvent
        self._cwd = Path.cwd()     # répertoire de lancement — racine des diffs git
        self._httpd: ThreadingHTTPServer | None = None

    # ── historique persisté ───────────────────────────────────────────────────

    def _load_history(self) -> list[dict]:
        try:
            return json.loads(self._history_path.read_text()) if self._history_path.exists() else []
        except Exception:
            return []

    def _save_history(self) -> None:
        try:
            self._history_path.write_text(json.dumps(self._history, ensure_ascii=False))
        except Exception:
            pass

    # ── connexion ─────────────────────────────────────────────────────────────

    def connect(self) -> None:
        """Ouvre la connexion persistante au gateway et démarre le reader."""
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.connect(str(self.socket_path))
        welcome_line = self._read_line()
        if welcome_line:
            self._welcome = decode(welcome_line)
        threading.Thread(
            target=self._reader_loop,
            daemon=True,
            name="web-socket-reader",
        ).start()

    # ── envoi vers gateway ────────────────────────────────────────────────────

    def send_input(self, text: str, session_id: str) -> None:
        self._active_session = session_id
        self._history.append({"role": "user", "content": text})
        self._save_history()
        self._current_assistant = ""
        with self._send_lock:
            assert self._sock
            self._sock.sendall(encode(InputEvent(text=text)))

    def send_command(self, cmd: str) -> None:
        if cmd == "/new":
            self._history.clear()
            self._current_assistant = ""
            self._save_history()
        with self._send_lock:
            assert self._sock
            self._sock.sendall(encode(CommandEvent(cmd=cmd)))

    def approve_permission(self, request_id: str, approved: bool) -> None:
        with self._perms_lock:
            entry = self._pending_perms.get(request_id)
        if entry:
            ev, result = entry
            result[0] = approved
            ev.set()

    # ── SSE queues ────────────────────────────────────────────────────────────

    def open_sse(self, session_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=500)
        with self._queues_lock:
            self._sse_queues[session_id] = q
        return q

    def close_sse(self, session_id: str) -> None:
        with self._queues_lock:
            self._sse_queues.pop(session_id, None)

    # ── reader loop ───────────────────────────────────────────────────────────

    def _reader_loop(self) -> None:
        """Thread daemon — lit les events gateway et les route vers les queues SSE."""
        while True:
            line = self._read_line()
            if line is None:
                self._broadcast({"type": "disconnected", "reason": "gateway_closed"})
                break
            self._dispatch(line)

    def _dispatch(self, line: str) -> None:
        event = decode(line)
        etype = event.get("type")
        sid = self._active_session or "default"

        if etype == "delta":
            delta = event.get("text", "")
            self._current_assistant += delta
            self._push(sid, {"type": "text_delta", "delta": delta})

        elif etype == "tool_start":
            self._push(sid, {
                "type": "tool_start",
                "tool": event.get("name", ""),
                "target": event.get("target", ""),
            })

        elif etype == "tool_result":
            self._push(sid, {
                "type": "tool_result",
                "tool": event.get("name", ""),
                "ok": bool(event.get("ok", True)),
            })

        elif etype == "permission_request":
            req_id = event.get("request_id", "")
            ev = threading.Event()
            result: list[bool] = [False]
            with self._perms_lock:
                self._pending_perms[req_id] = (ev, result)
            self._push(sid, {
                "type": "permission_request",
                "tool": event.get("tool_name", ""),
                "reason": event.get("reason", ""),
                "request_id": req_id,
            })
            ev.wait(timeout=30)
            with self._perms_lock:
                self._pending_perms.pop(req_id, None)
            with self._send_lock:
                assert self._sock
                self._sock.sendall(encode(
                    PermissionResponseEvent(request_id=req_id, approved=result[0])
                ))

        elif etype == "error":
            self._push(sid, {"type": "error", "error": event.get("message", "")})

        elif etype == "status":
            self._push(sid, {"type": "status", "message": event.get("message", "")})

        elif etype == "done":
            if self._current_assistant.strip():
                self._history.append({"role": "assistant", "content": self._current_assistant})
                self._save_history()
            self._current_assistant = ""
            self._push(sid, {"type": "done_turn"})
            self._active_session = None

    def _push(self, session_id: str, event: dict) -> None:
        with self._queues_lock:
            q = self._sse_queues.get(session_id)
        if q is not None:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    def _broadcast(self, event: dict | None) -> None:
        with self._queues_lock:
            queues = list(self._sse_queues.values())
        for q in queues:
            try:
                q.put_nowait(event)
            except queue.Full:
                pass

    def _read_line(self) -> str | None:
        assert self._sock
        while b"\n" not in self._buf:
            try:
                chunk = self._sock.recv(4096)
            except OSError:
                return None
            if not chunk:
                return None
            self._buf.extend(chunk)
        idx = self._buf.index(b"\n")
        line = self._buf[:idx].decode(errors="replace")
        del self._buf[:idx + 1]
        return line

    # ── HTTP server ───────────────────────────────────────────────────────────

    def serve_forever(self) -> None:
        handler = _make_handler(self)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._httpd.serve_forever()

    def shutdown(self) -> None:
        self._broadcast(None)
        if self._httpd:
            self._httpd.shutdown()
        if self._sock:
            try:
                self._sock.close()
            except OSError:
                pass

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}"


# ── HTTP handler ──────────────────────────────────────────────────────────────


def _make_handler(ws: WebServer):
    class Handler(BaseHTTPRequestHandler):

        def do_GET(self) -> None:
            parsed = urlparse(self.path)

            if parsed.path == "/":
                self._html(_ui_html())
                return

            if parsed.path == "/health":
                self._json({"ok": True, "agent": ws.agent_name})
                return

            if parsed.path == "/api/stream":
                query = parse_qs(parsed.query)
                sid = query.get("session_id", ["default"])[0]
                self._stream_sse(ws.open_sse(sid), sid)
                return

            if parsed.path == "/api/image":
                query = parse_qs(parsed.query)
                self._serve_image(query.get("path", [""])[0], ws.agent_name)
                return

            if parsed.path == "/api/history":
                self._json({"ok": True, "messages": ws._history})
                return

            if parsed.path == "/api/git/status":
                from marius.channels.web.git_helpers import git_changes
                self._json(git_changes(ws._cwd))
                return

            if parsed.path == "/api/git/diff":
                from marius.channels.web.git_helpers import git_diff
                query = parse_qs(parsed.query)
                file_path = query.get("path", [""])[0]
                self._json(git_diff(ws._cwd, file_path))
                return

            if parsed.path == "/api/info":
                self._json({
                    "ok": True,
                    "agent": ws.agent_name,
                    "model": ws._welcome.get("model", ""),
                    "provider": ws._welcome.get("provider", ""),
                    "skill_commands": _get_skill_commands(ws.agent_name),
                })
                return

            if parsed.path == "/api/models":
                self._json({"ok": True, "models": _get_models(ws)})
                return

            self._json({"ok": False, "error": "not_found"}, 404)

        def do_POST(self) -> None:
            parsed = urlparse(self.path)

            if parsed.path == "/api/message":
                try:
                    payload = self._read_json()
                    text = str(payload.get("text") or payload.get("message") or "").strip()
                    sid  = str(payload.get("session_id") or "default")
                except Exception as exc:
                    self._json({"ok": False, "error": str(exc)}, 400)
                    return
                if not text:
                    self._json({"ok": False, "error": "empty_message"}, 400)
                    return
                ws.send_input(text, sid)
                self._json({"ok": True, "session_id": sid})
                return

            if parsed.path == "/api/command":
                try:
                    payload = self._read_json()
                    cmd = str(payload.get("cmd") or "")
                except Exception as exc:
                    self._json({"ok": False, "error": str(exc)}, 400)
                    return
                if cmd not in ("/new", "/stop"):
                    self._json({"ok": False, "error": f"commande non reconnue : {cmd}"}, 400)
                    return
                ws.send_command(cmd)
                self._json({"ok": True})
                return

            if parsed.path == "/api/permission":
                try:
                    payload = self._read_json()
                    req_id   = str(payload.get("request_id") or "")
                    approved = bool(payload.get("approved", False))
                except Exception as exc:
                    self._json({"ok": False, "error": str(exc)}, 400)
                    return
                ws.approve_permission(req_id, approved)
                self._json({"ok": True})
                return

            if parsed.path == "/api/upload":
                try:
                    payload = self._read_json()
                    result  = _save_upload(ws.agent_name, payload)
                except Exception as exc:
                    self._json({"ok": False, "error": str(exc)}, 400)
                    return
                self._json(result)
                return

            if parsed.path == "/api/model":
                try:
                    payload = self._read_json()
                    model = str(payload.get("model") or "").strip()
                    if not model:
                        self._json({"ok": False, "error": "model manquant"}, 400)
                        return
                    ok = _set_model(ws, model)
                    self._json({"ok": ok})
                except Exception as exc:
                    self._json({"ok": False, "error": str(exc)}, 400)
                return

            self._json({"ok": False, "error": "not_found"}, 404)

        def _stream_sse(self, q: queue.Queue, sid: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    try:
                        event = q.get(timeout=_SSE_KEEPALIVE)
                    except queue.Empty:
                        self.wfile.write(b": keep-alive\n\n")
                        self.wfile.flush()
                        continue
                    if event is None:
                        self.wfile.write(b'data: {"type":"disconnected"}\n\n')
                        self.wfile.flush()
                        break
                    self.wfile.write(f"data: {json.dumps(event)}\n\n".encode())
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                ws.close_sse(sid)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            return json.loads(self.rfile.read(length).decode() or "{}")

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

        def _serve_image(self, path_str: str, agent_name: str) -> None:
            import mimetypes as _mt
            if not path_str:
                self._json({"error": "missing path"}, 400)
                return
            path = Path(path_str).resolve()
            uploads_dir = (Path.home() / ".marius" / "workspace" / agent_name / "uploads").resolve()
            if not str(path).startswith(str(uploads_dir)):
                self._json({"error": "forbidden"}, 403)
                return
            if not path.exists():
                self._json({"error": "not found"}, 404)
                return
            mime = _mt.guess_type(path.name)[0] or "application/octet-stream"
            body = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "private, max-age=3600")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_: Any) -> None:
            pass

    return Handler


# ── upload ────────────────────────────────────────────────────────────────────


def _get_skill_commands(agent_name: str) -> list[dict]:
    """Retourne les skill commands actives pour cet agent."""
    try:
        from marius.config.store import ConfigStore
        from marius.kernel.skills import SkillReader, collect_skill_commands
        cfg = ConfigStore().load()
        if not cfg:
            return []
        agent = cfg.get_agent(agent_name)
        if not agent:
            return []
        cmds = collect_skill_commands(SkillReader().load_all(agent.skills or []))
        return [{"name": f"/{n}", "desc": sc.description or sc.name} for n, sc in cmds.items()]
    except Exception:
        return []


def _get_models(ws: WebServer) -> list[str]:
    try:
        from marius.provider_config.fetcher import ModelFetchError, fetch_models
        from marius.provider_config.store import ProviderStore
        from marius.config.store import ConfigStore
        from dataclasses import replace as dc_replace
        cfg = ConfigStore().load()
        if not cfg:
            return []
        agent = cfg.get_agent(ws.agent_name)
        if not agent:
            return []
        providers = ProviderStore().load()
        entry = next((p for p in providers if p.id == agent.provider_id), None)
        if not entry:
            return []
        if agent.model and agent.model != entry.model:
            entry = dc_replace(entry, model=agent.model)
        return fetch_models(entry)
    except Exception:
        return []


def _set_model(ws: WebServer, model: str) -> bool:
    try:
        from marius.config.store import ConfigStore
        from marius.provider_config.store import ProviderStore
        from dataclasses import replace as dc_replace
        cfg = ConfigStore().load()
        if not cfg:
            return False
        agent = cfg.get_agent(ws.agent_name)
        if not agent:
            return False
        cfg.agents[ws.agent_name] = dc_replace(agent, model=model)
        ConfigStore().save(cfg)
        return True
    except Exception:
        return False


_MIME_EXT: dict[str, str] = {
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
    "image/gif": ".gif",  "image/webp": ".webp", "image/bmp": ".bmp",
    "image/svg+xml": ".svg", "application/pdf": ".pdf",
    "text/plain": ".txt", "text/markdown": ".md",
}


def _save_upload(agent_name: str, payload: dict) -> dict:
    filename  = str(payload.get("filename") or "upload.bin")
    data_b64  = str(payload.get("data") or "")
    mime_type = str(payload.get("mime_type") or "")

    uploads_dir = Path.home() / ".marius" / "workspace" / agent_name / "uploads"
    uploads_dir.mkdir(parents=True, exist_ok=True)

    safe = "".join(c for c in filename if c.isalnum() or c in "._-")[:64] or "upload"

    # Ajoute l'extension si absente et que le MIME type est connu
    if "." not in safe and mime_type in _MIME_EXT:
        safe += _MIME_EXT[mime_type]

    path = uploads_dir / f"{uuid.uuid4().hex[:8]}_{safe}"
    path.write_bytes(base64.b64decode(data_b64))
    return {"ok": True, "path": str(path), "name": safe}


# ── UI HTML ───────────────────────────────────────────────────────────────────


import functools


@functools.cache
def _ui_html() -> str:
    p = Path(__file__).parent / "ui.html"
    return p.read_text(encoding="utf-8") if p.exists() else "<html><body>ui.html manquant.</body></html>"
