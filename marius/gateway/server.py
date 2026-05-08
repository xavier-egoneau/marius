"""Serveur gateway Marius.

Processus persistant par agent : maintient la session et la mémoire
entre les reconnexions. Une seule connexion cliente à la fois.

Threading :
- Thread principal : accepte les connexions, lit le socket
- Thread de tour   : exécute orchestrator.run_turn, écrit en streaming
- Les requêtes de permission bloquent le thread de tour jusqu'à
  réception de PermissionResponseEvent depuis le client.
"""

from __future__ import annotations

import os
import signal
import socket
import sys
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from marius.adapters.http_provider import make_adapter
from marius.kernel.compaction import CompactionConfig
from marius.kernel.context_factory import build_system_prompt
from marius.kernel.context_window import FALLBACK_CONTEXT_WINDOW, resolve_context_window
from marius.kernel.contracts import Message, Role, ToolCall, ToolResult
from marius.kernel.memory_context import format_memory_block
from marius.kernel.permission_guard import PermissionGuard
from marius.kernel.runtime import RuntimeOrchestrator, TurnInput
from marius.kernel.session import SessionRuntime
from marius.kernel.tool_router import ToolRouter
from marius.provider_config.contracts import ProviderEntry
from marius.provider_config.registry import PROVIDER_REGISTRY
from marius.storage.memory_store import MemoryStore
from marius.storage.session_corpus import SessionRecord, write_session_file
from marius.tools.filesystem import LIST_DIR, READ_FILE, WRITE_FILE
from marius.tools.memory import make_memory_tool
from marius.tools.shell import RUN_BASH
from marius.tools.skills import SKILL_VIEW
from marius.tools.web import WEB_FETCH, WEB_SEARCH

from .protocol import (
    CommandEvent, DeltaEvent, DoneEvent, ErrorEvent, InputEvent,
    PermissionRequestEvent, PongEvent, StatusEvent, ToolResultEvent,
    ToolStartEvent, WelcomeEvent, decode, encode, tool_target,
)
from .workspace import (
    ensure_workspace, memory_db_path, pid_path, sessions_dir, socket_path,
)

_STATIC_TOOLS = {
    "read_file":  READ_FILE,
    "list_dir":   LIST_DIR,
    "write_file": WRITE_FILE,
    "run_bash":   RUN_BASH,
    "web_fetch":  WEB_FETCH,
    "web_search": WEB_SEARCH,
    "skill_view": SKILL_VIEW,
}


class _LineReader:
    """Lecteur de lignes sur socket Unix."""

    def __init__(self, conn: socket.socket) -> None:
        self._conn = conn
        self._buf = ""

    def readline(self) -> str | None:
        while "\n" not in self._buf:
            try:
                chunk = self._conn.recv(4096)
            except OSError:
                return None
            if not chunk:
                return None
            self._buf += chunk.decode(errors="replace")
        line, self._buf = self._buf.split("\n", 1)
        return line


class GatewayServer:
    def __init__(
        self,
        agent_name: str,
        entry: ProviderEntry,
        agent_config: Any,
        permission_mode: str = "limited",
    ) -> None:
        self.agent_name = agent_name
        self.entry = entry
        self.agent_config = agent_config
        self.permission_mode = permission_mode

        ws = ensure_workspace(agent_name)
        self.workspace = ws
        self.memory_store = MemoryStore(memory_db_path(agent_name))

        active_skills = list(agent_config.skills) if agent_config else []
        self.system_prompt, self.loaded_context = build_system_prompt(
            ws,
            active_skills=active_skills or None,
        )
        active_memories = self.memory_store.get_active_context(ws)
        memory_block = format_memory_block(active_memories)
        if memory_block:
            self.system_prompt = f"{self.system_prompt}\n\n{memory_block.text}".strip()

        self._send_lock = threading.Lock()
        self._conn: socket.socket | None = None
        self._pending_perms: dict[str, tuple[threading.Event, list[bool]]] = {}

        guard = PermissionGuard(
            mode=permission_mode,
            cwd=ws,
            on_ask=self._on_ask,
        )
        enabled_tools = list(agent_config.tools) if agent_config else None
        self.tool_router = self._build_tool_router(enabled_tools, guard, ws)

        self.session = SessionRuntime(
            session_id=agent_name,
            metadata={"provider": entry.name, "model": entry.model},
        )
        adapter = make_adapter(entry)
        window = self._resolve_window(entry)
        self.orchestrator = RuntimeOrchestrator(
            provider=adapter,
            tool_router=self.tool_router,
            compaction_config=CompactionConfig(context_window_tokens=window),
        )
        self._opened_at = datetime.now(timezone.utc).isoformat()

    # ── permission interactive ────────────────────────────────────────────────

    def _on_ask(self, tool_name: str, arguments: dict, reason: str) -> bool:
        conn = self._conn
        if conn is None:
            return False
        import uuid
        req_id = uuid.uuid4().hex[:8]
        ev: threading.Event = threading.Event()
        result: list[bool] = [False]
        self._pending_perms[req_id] = (ev, result)
        try:
            self._send(conn, PermissionRequestEvent(
                tool_name=tool_name,
                reason=reason,
                request_id=req_id,
            ))
            ev.wait(timeout=30)
        finally:
            self._pending_perms.pop(req_id, None)
        return result[0]

    # ── helpers ───────────────────────────────────────────────────────────────

    def _send(self, conn: socket.socket, event: Any) -> None:
        with self._send_lock:
            try:
                conn.sendall(encode(event))
            except OSError:
                pass

    def _build_tool_router(
        self, enabled_tools: list[str] | None, guard: PermissionGuard, cwd: Path
    ) -> ToolRouter:
        memory_tool = make_memory_tool(self.memory_store, cwd)
        registry = {**_STATIC_TOOLS, "memory": memory_tool}
        if enabled_tools is None:
            entries = list(registry.values())
        else:
            entries = [registry[n] for n in enabled_tools if n in registry]
            if memory_tool not in entries:
                entries.insert(0, memory_tool)
        return ToolRouter(entries, guard=guard)

    @staticmethod
    def _resolve_window(entry: ProviderEntry) -> int:
        defn = PROVIDER_REGISTRY.get(entry.provider)
        if defn is None:
            return FALLBACK_CONTEXT_WINDOW
        api_resolver = None
        if defn.context_window_api_endpoint:
            from marius.adapters.context_window import make_api_resolver
            api_resolver = make_api_resolver(
                base_url=entry.base_url,
                api_endpoint=defn.context_window_api_endpoint,
                model=entry.model,
                api_key=entry.api_key,
            )
        return resolve_context_window(
            model=entry.model,
            strategy=defn.context_window_strategy,
            api_resolver=api_resolver,
        )

    # ── boucle principale ─────────────────────────────────────────────────────

    def serve(self) -> None:
        sock_path = socket_path(self.agent_name)
        if sock_path.exists():
            sock_path.unlink()

        pid_path(self.agent_name).write_text(str(os.getpid()), encoding="utf-8")

        def _sigterm(sig, frame):
            sys.exit(0)
        signal.signal(signal.SIGTERM, _sigterm)

        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(str(sock_path))
        server_sock.listen(1)

        try:
            while True:
                conn, _ = server_sock.accept()
                self._conn = conn
                try:
                    self._handle_connection(conn)
                except Exception:
                    pass
                finally:
                    self._conn = None
                    try:
                        conn.close()
                    except OSError:
                        pass
        finally:
            server_sock.close()
            if sock_path.exists():
                sock_path.unlink()
            pf = pid_path(self.agent_name)
            if pf.exists():
                pf.unlink()
            self._write_corpus()

    def _handle_connection(self, conn: socket.socket) -> None:
        self._send(conn, WelcomeEvent(
            agent=self.agent_name,
            model=self.entry.model,
            provider=self.entry.name,
            loaded_context=self.loaded_context,
        ))

        reader = _LineReader(conn)
        turn_thread: threading.Thread | None = None
        stop_event: threading.Event | None = None

        while True:
            line = reader.readline()
            if line is None:
                if stop_event:
                    stop_event.set()
                break

            event = decode(line)
            etype = event.get("type")

            if etype == "ping":
                self._send(conn, PongEvent())

            elif etype == "permission_response":
                req_id = event.get("request_id", "")
                approved = bool(event.get("approved", False))
                if req_id in self._pending_perms:
                    ev, result = self._pending_perms[req_id]
                    result[0] = approved
                    ev.set()

            elif etype == "command":
                cmd = event.get("cmd", "")
                if cmd == "/stop" and stop_event:
                    stop_event.set()
                elif cmd == "/new":
                    if turn_thread is None or not turn_thread.is_alive():
                        self.session.state.turns.clear()
                        self.session.state.compaction_notices.clear()
                        self._send(conn, StatusEvent(message="Nouvelle conversation démarrée."))

            elif etype == "input":
                if turn_thread and turn_thread.is_alive():
                    continue  # ignore if turn running
                stop_event = threading.Event()
                text = event.get("text", "")
                turn_thread = threading.Thread(
                    target=self._run_turn,
                    args=(conn, text, stop_event),
                    daemon=True,
                )
                turn_thread.start()

    def _run_turn(
        self, conn: socket.socket, text: str, stop_event: threading.Event
    ) -> None:
        user_message = Message(
            role=Role.USER,
            content=text,
            created_at=datetime.now(timezone.utc),
        )

        def on_text_delta(delta: str) -> None:
            if stop_event.is_set():
                raise KeyboardInterrupt
            self._send(conn, DeltaEvent(text=delta))

        def on_tool_start(call: ToolCall) -> None:
            self._send(conn, ToolStartEvent(
                name=call.name,
                target=tool_target(call.name, call.arguments),
            ))

        def on_tool_result(call: ToolCall, result: ToolResult) -> None:
            self._send(conn, ToolResultEvent(name=call.name, ok=result.ok))

        try:
            self.orchestrator.run_turn(
                TurnInput(
                    session=self.session,
                    user_message=user_message,
                    system_prompt=self.system_prompt,
                ),
                on_text_delta=on_text_delta,
                on_tool_start=on_tool_start,
                on_tool_result=on_tool_result,
            )
        except KeyboardInterrupt:
            self._send(conn, ErrorEvent(message="Inférence interrompue."))
        except Exception as exc:
            self._send(conn, ErrorEvent(message=str(exc)))
        finally:
            self._send(conn, DoneEvent())

    def _write_corpus(self) -> None:
        try:
            turns = len(self.session.state.turns)
            if turns == 0:
                return
            record = SessionRecord(
                project=self.agent_name,
                cwd=str(self.workspace),
                opened_at=self._opened_at,
                closed_at=datetime.now(timezone.utc).isoformat(),
                turns=turns,
            )
            write_session_file(record, sessions_dir(self.agent_name))
        except Exception:
            pass
