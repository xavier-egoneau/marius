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

import json
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
from marius.kernel.skills import SkillCommand, SkillReader, collect_skill_commands
from marius.kernel.context_window import FALLBACK_CONTEXT_WINDOW, resolve_context_window
from marius.kernel.contracts import Message, Role, ToolCall, ToolResult
from marius.kernel.memory_context import format_memory_block
from marius.kernel.permission_guard import PermissionGuard
from marius.kernel.posture import maybe_activate_dev_posture, uses_dev_posture
from marius.kernel.runtime import RuntimeOrchestrator, TurnInput
from marius.kernel.session import SessionRuntime
from marius.kernel.session_observations import format_session_observations, observe_tool_result
from marius.kernel.tool_router import ToolRouter
from marius.provider_config.contracts import ProviderEntry
from marius.provider_config.registry import PROVIDER_REGISTRY
from marius.storage.memory_store import MemoryStore
from marius.storage.log_store import log_event, preview
from marius.storage.session_corpus import SessionRecord, write_session_file
from marius.tools.factory import build_tool_entries

from .protocol import (
    CommandEvent, DeltaEvent, DoneEvent, ErrorEvent, InputEvent,
    PermissionRequestEvent, PongEvent, StatusEvent, ToolResultEvent,
    ToolStartEvent, WelcomeEvent, decode, encode, tool_target,
)
from .workspace import (
    ensure_workspace,
    memory_db_path, pid_path, reminders_path, sessions_dir, socket_path,
    web_history_path,
)

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

        from marius.storage.reminders_store import RemindersStore
        self.reminders_store = RemindersStore(reminders_path(agent_name))

        self.active_skills = list(agent_config.skills) if agent_config else []
        self.skill_commands: dict[str, SkillCommand] = collect_skill_commands(
            SkillReader().load_all(self.active_skills)
        ) if self.active_skills else {}
        self.system_prompt, self.loaded_context = build_system_prompt(
            ws,
            active_skills=self.active_skills or None,
            agent_name=agent_name,
        )
        active_memories = self.memory_store.get_active_context(ws)
        self.memory_block = format_memory_block(active_memories)
        if self.memory_block:
            self.system_prompt = f"{self.system_prompt}\n\n{self.memory_block.text}".strip()

        self._send_lock = threading.Lock()
        self._turn_lock  = threading.Lock()   # sérialise CLI + Telegram
        self._conn: socket.socket | None = None
        self._pending_perms: dict[str, tuple[threading.Event, list[bool]]] = {}
        self.telegram_chat_id: int | None = None   # mémorisé pour pushs daily

        guard = PermissionGuard(
            mode=permission_mode,
            cwd=ws,
            on_ask=self._on_ask,
        )
        enabled_tools = list(agent_config.tools) if agent_config else None
        self.tool_router = self._build_tool_router(enabled_tools, guard, ws, entry, permission_mode)

        self.session = SessionRuntime(
            session_id=agent_name,
            metadata={"provider": entry.name, "model": entry.model},
        )
        restored_turns = _restore_session_from_web_history(
            self.session,
            web_history_path(agent_name),
        )
        adapter = make_adapter(entry)
        window = self._resolve_window(entry)
        self.orchestrator = RuntimeOrchestrator(
            provider=adapter,
            tool_router=self.tool_router,
            compaction_config=CompactionConfig(context_window_tokens=window),
        )
        self._opened_at = datetime.now(timezone.utc).isoformat()
        log_event("gateway_start", {
            "agent": agent_name,
            "cwd": str(ws),
            "provider": entry.name,
            "provider_kind": entry.provider,
            "model": entry.model,
            "permission_mode": permission_mode,
            "tools": enabled_tools or "all",
            "restored_turns": restored_turns,
        })

        # Scheduler + reminders — délégués à GatewayScheduler
        from .scheduler_runner import GatewayScheduler
        self._scheduler_runner = GatewayScheduler(
            agent_name=agent_name,
            workspace=ws,
            memory_store=self.memory_store,
            entry=entry,
            active_skills=self.active_skills,
            agent_config=agent_config,
            reminders_store=self.reminders_store,
            get_telegram_chat_id=lambda: self.telegram_chat_id,
        )

    # ── Telegram channel ──────────────────────────────────────────────────────

    def _start_telegram(self) -> None:
        from marius.channels.telegram.config import load as load_tg_cfg
        from marius.channels.telegram.poller import TelegramPoller
        from .workspace import telegram_offset_path

        cfg = load_tg_cfg()
        if not cfg or not cfg.enabled or cfg.agent_name != self.agent_name:
            return

        self._telegram_poller = TelegramPoller(
            cfg=cfg,
            gateway=self,
            offset_path=telegram_offset_path(self.agent_name),
        )
        self._telegram_poller.start()

    def run_turn_for_telegram(self, text: str) -> str:
        """Exécute un tour depuis Telegram. Bloquant, sérialisé via turn_lock."""
        from marius.kernel.contracts import Message, Role
        text = self.resolve_skill_command(text)
        cancel_event = threading.Event()
        response_parts: list[str] = []

        log_event("turn_start", {
            "session_id": self.agent_name,
            "agent": self.agent_name,
            "channel": "telegram",
            "provider": self.entry.name,
            "model": self.entry.model,
            "user_preview": preview(text),
        })

        def on_text_delta(delta: str) -> None:
            if cancel_event.is_set():
                raise KeyboardInterrupt
            response_parts.append(delta)

        def on_tool_start(call: ToolCall) -> None:
            log_event("tool_start", {"session_id": self.agent_name, "channel": "telegram", "tool": call.name})

        def on_tool_result(call: ToolCall, result: ToolResult) -> None:
            observe_tool_result(self.session.state.metadata, call, result, project_root=self.workspace)
            log_event("tool_result", {
                "session_id": self.agent_name, "channel": "telegram",
                "tool": call.name, "ok": result.ok,
            })

        user_message = Message(
            role=Role.USER,
            content=text,
            created_at=datetime.now(timezone.utc),
        )
        from marius.kernel.runtime import TurnInput
        with self._turn_lock:
            try:
                output = self.orchestrator.run_turn(
                    TurnInput(
                        session=self.session,
                        user_message=user_message,
                        system_prompt=self._system_prompt_for_session(),
                    ),
                    on_text_delta=on_text_delta,
                    on_tool_start=on_tool_start,
                    on_tool_result=on_tool_result,
                )
                response = "".join(response_parts)
                log_event("turn_done", {
                    "session_id": self.agent_name, "channel": "telegram",
                    "model": self.entry.model,
                    "tool_results": len(output.tool_results),
                    "assistant_preview": preview(response),
                })
                return response
            except KeyboardInterrupt:
                return "".join(response_parts)
            except Exception as exc:
                log_event("turn_error", {"session_id": self.agent_name, "channel": "telegram", "error": str(exc)})
                return f"Erreur : {exc}"

    def new_conversation(self) -> None:
        """Réinitialise la session (appelable depuis Telegram /new ou web)."""
        self.session.state.turns.clear()
        self.session.state.compaction_notices.clear()
        self.session.state.derived_context_summary = ""
        self.session.state.derived_context_summary_message = None

    def resolve_skill_command(self, text: str) -> str:
        """Si text est une commande skill connue, retourne le prompt injecté.

        Ex: "/plan construire une API REST" → contenu de core/plan.md + args.
        Sinon retourne text inchangé.
        """
        if not text.startswith("/"):
            return text
        parts = text.split(maxsplit=1)
        cmd_name = parts[0].lstrip("/").lower()
        skill_cmd = self.skill_commands.get(cmd_name)
        if not skill_cmd:
            return text
        arg = parts[1] if len(parts) > 1 else ""
        return f"{skill_cmd.prompt}\n\n{arg}".strip() if skill_cmd.prompt else arg

    def list_models(self) -> list[str]:
        """Retourne les modèles disponibles pour le provider actuel."""
        from marius.provider_config.fetcher import ModelFetchError, fetch_models
        try:
            return fetch_models(self.entry)
        except ModelFetchError:
            return []

    def set_model(self, model: str) -> bool:
        """Change le modèle à chaud et persiste dans la config agent.

        Retourne True si le changement a été appliqué.
        """
        from dataclasses import replace
        from marius.config.store import ConfigStore

        new_entry = replace(self.entry, model=model)
        new_adapter = make_adapter(new_entry)
        self.entry = new_entry
        self.orchestrator.provider = new_adapter

        # Persistance dans la config agent
        cfg_store = ConfigStore()
        cfg = cfg_store.load()
        if cfg:
            agent_cfg = cfg.get_agent(self.agent_name)
            if agent_cfg is not None:
                cfg.agents[self.agent_name] = replace(agent_cfg, model=model)
                cfg_store.save(cfg)
        return True

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
        self,
        enabled_tools: list[str] | None,
        guard: PermissionGuard,
        cwd: Path,
        entry: ProviderEntry | None = None,
        permission_mode: str = "limited",
    ) -> ToolRouter:
        from marius.tools.reminders import make_reminders_tool
        from marius.tools.spawn_agent import make_spawn_agent_tool

        reminders_tool = make_reminders_tool(
            self.reminders_store,
            get_chat_id=lambda: self.telegram_chat_id,
        )
        base_entries = build_tool_entries(
            enabled_tools,
            self.memory_store,
            cwd,
            extras={"reminders": reminders_tool},
        )

        if entry is not None and (enabled_tools is None or "spawn_agent" in enabled_tools):
            spawn_tool = make_spawn_agent_tool(
                entry,
                base_entries,
                permission_mode=permission_mode,
                cwd=cwd,
            )
            base_entries = [*base_entries, spawn_tool]

        return ToolRouter(base_entries, guard=guard)

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

        # Telegram poller (thread daemon, si configuré pour cet agent)
        self._telegram_poller = None
        self._start_telegram()

        def _sigterm(sig, frame):
            if self._telegram_poller:
                self._telegram_poller.stop()
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
        text = self.resolve_skill_command(text)
        user_message = Message(
            role=Role.USER,
            content=text,
            created_at=datetime.now(timezone.utc),
        )
        log_event("turn_start", {
            "session_id": self.agent_name,
            "agent": self.agent_name,
            "cwd": str(self.workspace),
            "provider": self.entry.name,
            "provider_kind": self.entry.provider,
            "model": self.entry.model,
            "user_preview": preview(text),
        })

        def on_text_delta(delta: str) -> None:
            if stop_event.is_set():
                raise KeyboardInterrupt
            self._send(conn, DeltaEvent(text=delta))

        def on_tool_start(call: ToolCall) -> None:
            target = tool_target(call.name, call.arguments)
            if maybe_activate_dev_posture(
                self.session.state.metadata,
                self.active_skills,
                call,
                self.workspace,
            ):
                log_event("posture_switch", {
                    "session_id": self.agent_name,
                    "agent": self.agent_name,
                    "posture": self.session.state.metadata.get("posture"),
                    "trigger_tool": call.name,
                    "target": preview(target, limit=200),
                })
            log_event("tool_start", {
                "session_id": self.agent_name,
                "tool": call.name,
                "target": preview(target, limit=200),
            })
            self._send(conn, ToolStartEvent(
                name=call.name,
                target=target,
            ))

        def on_tool_result(call: ToolCall, result: ToolResult) -> None:
            observe_tool_result(self.session.state.metadata, call, result, project_root=self.workspace)
            log_event("tool_result", {
                "session_id": self.agent_name,
                "tool": call.name,
                "ok": result.ok,
                "summary_preview": preview(result.summary, limit=300),
                "error": preview(result.error or "", limit=300),
            })
            self._send(conn, ToolResultEvent(name=call.name, ok=result.ok))

        try:
            system_prompt = self._system_prompt_for_session()
            with self._turn_lock:
                output = self.orchestrator.run_turn(
                    TurnInput(
                        session=self.session,
                        user_message=user_message,
                        system_prompt=system_prompt,
                    ),
                    on_text_delta=on_text_delta,
                    on_tool_start=on_tool_start,
                    on_tool_result=on_tool_result,
                )
            if output.assistant_message is not None:
                content = output.assistant_message.content
                event_name = "turn_empty_response" if not content.strip() else "turn_done"
                log_event(event_name, {
                    "session_id": self.agent_name,
                    "agent": self.agent_name,
                    "provider": self.entry.name,
                    "provider_kind": self.entry.provider,
                    "model": self.entry.model,
                    "tool_results": len(output.tool_results),
                    "assistant_preview": preview(content),
                    "input_tokens": output.usage.provider_input_tokens,
                    "estimated_input_tokens": output.usage.estimated_input_tokens,
                })
        except KeyboardInterrupt:
            log_event("turn_interrupted", {"session_id": self.agent_name, "agent": self.agent_name})
            self._send(conn, ErrorEvent(message="Inférence interrompue."))
        except Exception as exc:
            log_event("turn_unexpected_error", {
                "session_id": self.agent_name,
                "agent": self.agent_name,
                "provider": self.entry.name,
                "model": self.entry.model,
                "error": str(exc),
                "error_type": type(exc).__name__,
            })
            self._send(conn, ErrorEvent(message=str(exc)))
        finally:
            self._send(conn, DoneEvent())

    def _system_prompt_for_session(self) -> str:
        system_prompt, _loaded = build_system_prompt(
            self.workspace,
            active_skills=self.active_skills or None,
            agent_name=self.agent_name,
            dev_posture=uses_dev_posture(self.active_skills, self.session.state.metadata),
        )
        if self.memory_block:
            system_prompt = f"{system_prompt}\n\n{self.memory_block.text}".strip()
        observations = format_session_observations(self.session.state.metadata)
        if observations:
            system_prompt = f"{system_prompt}\n\n{observations}".strip()
        return system_prompt

    def _write_corpus(self) -> None:
        try:
            turns = len(self.session.state.turns)
            if turns == 0:
                return
            from marius.storage.session_corpus import build_transcript
            messages: list = []
            for turn in self.session.state.turns:
                messages.extend(turn.input_messages)
                if turn.assistant_message:
                    messages.append(turn.assistant_message)
            record = SessionRecord(
                project=self.agent_name,
                cwd=str(self.workspace),
                opened_at=self._opened_at,
                closed_at=datetime.now(timezone.utc).isoformat(),
                turns=turns,
                transcript=build_transcript(messages),
            )
            write_session_file(record, sessions_dir(self.agent_name))
        except Exception:
            pass


def _restore_session_from_web_history(session: SessionRuntime, history_path: Path) -> int:
    """Best-effort restore of recent visible turns after a gateway restart."""
    try:
        raw = json.loads(history_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(raw, list):
        return 0
    return _hydrate_session_from_visible_history(session, raw)


def _hydrate_session_from_visible_history(
    session: SessionRuntime,
    history: list[dict[str, Any]],
    *,
    max_turns: int = 20,
) -> int:
    """Hydrate a fresh kernel session from persisted visible user/assistant pairs.

    Web history is not a full runtime snapshot: it has no tool calls or artifacts.
    Restoring the visible pairs is still enough to keep follow-up turns coherent
    after a gateway restart instead of showing an old UI conversation backed by
    an empty kernel session.
    """
    if session.state.turns:
        return 0

    pairs: list[tuple[str, str]] = []
    pending_user: str | None = None
    for item in history:
        role = str(item.get("role") or "")
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        if role == "user":
            pending_user = content
        elif role == "assistant" and pending_user is not None:
            pairs.append((pending_user, content))
            pending_user = None

    if max_turns >= 0:
        pairs = pairs[-max_turns:]

    now = datetime.now(timezone.utc)
    for user_content, assistant_content in pairs:
        turn = session.start_turn(
            user_message=Message(
                role=Role.USER,
                content=user_content,
                created_at=now,
                metadata={"source": "web_history"},
            ),
            metadata={"status": "restored", "source": "web_history"},
        )
        session.finish_turn(
            turn.id,
            assistant_message=Message(
                role=Role.ASSISTANT,
                content=assistant_content,
                created_at=now,
                metadata={"source": "web_history"},
            ),
        )
        turn.metadata["status"] = "restored"

    return len(pairs)
