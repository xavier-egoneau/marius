"""Serveur gateway Marius.

Processus persistant par agent : maintient la session et la mémoire
entre les reconnexions. Plusieurs surfaces peuvent rester connectées.

Threading :
- Thread principal : accepte les connexions
- Threads clients  : lisent chaque socket
- Thread de tour   : exécute orchestrator.run_turn, écrit en streaming
- Les requêtes de permission bloquent le thread de tour jusqu'à
  réception de PermissionResponseEvent depuis le client.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import signal
import socket
import sys
import threading
import fcntl
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from marius.adapters.http_provider import make_adapter
from marius.config.contracts import effective_tools_for_agent
from marius.kernel.compaction import CompactionConfig
from marius.kernel.context_factory import build_system_prompt
from marius.kernel.skills import SkillCommand, SkillReader, collect_skill_commands
from marius.kernel.context_window import FALLBACK_CONTEXT_WINDOW, resolve_context_window
from marius.kernel.contracts import Artifact, ArtifactType, Message, Role, ToolCall, ToolResult
from marius.kernel.memory_context import format_memory_block
from marius.kernel.permission_guard import PermissionGuard
from marius.kernel.posture import maybe_activate_dev_posture, uses_dev_posture
from marius.kernel.runtime import RuntimeOrchestrator, TurnInput
from marius.kernel.session import SessionRuntime
from marius.kernel.session_observations import format_session_observations, observe_tool_result
from marius.kernel.tool_router import ToolRouter
from marius.provider_config.contracts import ProviderEntry
from marius.provider_config.registry import PROVIDER_REGISTRY
from marius.render.adapter import RenderSurface, render_turn_output
from marius.storage.memory_store import MemoryStore
from marius.storage.approval_store import ApprovalStore
from marius.storage.allow_root_store import AllowRootStore
from marius.storage.log_store import log_event, preview
from marius.storage.project_store import ProjectStore
from marius.storage.session_corpus import SessionRecord, write_session_file
from marius.storage.ui_history import FileVisibleConversationStore
from marius.tools.factory import build_tool_entries

from .protocol import (
    CommandEvent, DeltaEvent, DoneEvent, ErrorEvent, InputEvent,
    PermissionRequestEvent, PongEvent, StatusEvent, ToolResultEvent,
    ToolStartEvent, VisibleEvent, VisibleResetEvent, WelcomeEvent,
    decode, encode, tool_target,
)
from .workspace import (
    ensure_workspace, lock_path,
    memory_db_path, pid_path, reminders_path, sessions_dir, socket_path,
    telegram_chat_path, web_conversations_dir, web_history_path,
)
from .scheduler_runner import GatewayScheduler

_PERMISSION_TIMEOUT_SECONDS = 300
_ATTACHMENT_RE = re.compile(r"\[fichier joint : ([^\]]+)\]")
_NATIVE_IMAGE_MIME_TYPES = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}


def _trusted_roots_for_active_project(
    *,
    permission_mode: str,
    workspace: Path,
    allow_store: AllowRootStore,
) -> tuple[Path, ...]:
    roots = tuple(root.expanduser().resolve(strict=False) for root in allow_store.paths())
    try:
        active = ProjectStore().get_active()
    except Exception:
        return roots
    if active is None:
        return roots
    path = str(active.path or "").strip()
    if not path:
        return roots
    try:
        requested_root = Path(path).expanduser().resolve(strict=False)
    except (OSError, RuntimeError):
        return roots
    if _is_under_root(requested_root, roots) or _is_under_root(requested_root, (workspace,)):
        return roots

    from marius.kernel.guardian_policy import (
        AllowExpansionReason,
        AllowExpansionRequest,
        AllowExpansionStatus,
        DefaultGuardianPolicy,
    )
    from marius.kernel.project_context import PermissionMode

    try:
        mode = PermissionMode(permission_mode)
    except ValueError:
        mode = PermissionMode.LIMITED
    decision = DefaultGuardianPolicy().review_allow_expansion(
        AllowExpansionRequest(
            permission_mode=mode,
            workspace_root=workspace,
            current_allowed_roots=(workspace, *roots),
            requested_root=requested_root,
            reason=AllowExpansionReason.ACTIVATE_PROJECT,
            explicit_user_request=True,
        )
    )
    if decision.status is AllowExpansionStatus.ALLOW:
        for root in decision.roots_to_add:
            allow_store.add(root, reason=decision.code.value)
        roots = tuple(root.expanduser().resolve(strict=False) for root in allow_store.paths())
    return roots


def _is_under_root(path: Path, roots: tuple[Path, ...]) -> bool:
    normalized = path.expanduser().resolve(strict=False)
    for root in roots:
        normalized_root = root.expanduser().resolve(strict=False)
        if normalized == normalized_root or normalized_root in normalized.parents:
            return True
    return False


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
        self.approval_store = ApprovalStore()
        self.allow_root_store = AllowRootStore()

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
        self._turn_lock  = threading.RLock()  # sérialise CLI + Telegram + resets
        self._conn: socket.socket | None = None
        self._connections: set[socket.socket] = set()
        self._connections_lock = threading.Lock()
        self._pending_perms: dict[str, tuple[threading.Event, list[bool]]] = {}
        self._turn_context = threading.local()
        self.telegram_chat_id: int | None = self._load_telegram_chat_id()
        allowed_roots_provider = lambda: _trusted_roots_for_active_project(
            permission_mode=permission_mode,
            workspace=ws,
            allow_store=self.allow_root_store,
        )
        self.allowed_roots = allowed_roots_provider()

        guard = PermissionGuard(
            mode=permission_mode,
            cwd=ws,
            allowed_roots=self.allowed_roots,
            allowed_roots_provider=allowed_roots_provider,
            on_ask=self._on_ask,
            approval_lookup=self.approval_store.lookup,
            approval_recorder=self._record_approval,
        )
        enabled_tools = effective_tools_for_agent(
            list(agent_config.disabled_tools or []) if agent_config else None,
            getattr(agent_config, "role", None),
            self.active_skills,
        )
        self._ensure_search_backend(enabled_tools)
        self.tool_router = self._build_tool_router(
            enabled_tools,
            guard,
            ws,
            entry,
            permission_mode,
            allowed_roots_provider=allowed_roots_provider,
        )

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
        self._recover_interrupted_tasks()
        log_event("gateway_start", {
            "agent": agent_name,
            "cwd": str(ws),
            "provider": entry.name,
            "provider_kind": entry.provider,
            "model": entry.model,
            "permission_mode": permission_mode,
            "allowed_roots": [str(root) for root in self.allowed_roots],
            "tools": enabled_tools or "all",
            "restored_turns": restored_turns,
        })

        # Scheduler + reminders — délégués à GatewayScheduler
        self._scheduler_runner = GatewayScheduler(
            agent_name=agent_name,
            workspace=ws,
            memory_store=self.memory_store,
            entry=entry,
            active_skills=self.active_skills,
            agent_config=agent_config,
            reminders_store=self.reminders_store,
            get_telegram_chat_id=lambda: self.telegram_chat_id,
            permission_mode=permission_mode,
        )

    def _recover_interrupted_tasks(self) -> None:
        try:
            from marius.storage.task_store import TaskStore

            recovered = TaskStore().recover_interrupted_running(self.agent_name)
            for task in recovered:
                log_event("task_recovered_interrupted", {
                    "agent": self.agent_name,
                    "task_id": task.id,
                    "status": task.status,
                    "last_error": task.last_error,
                })
        except Exception as exc:
            log_event("task_recovery_failed", {
                "agent": self.agent_name,
                "error": str(exc)[:300],
            })

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

    def _load_telegram_chat_id(self) -> int | None:
        try:
            text = telegram_chat_path(self.agent_name).read_text(encoding="utf-8").strip()
            return int(text) if text else None
        except (OSError, ValueError):
            return None

    def remember_telegram_chat_id(self, chat_id: int) -> None:
        self.telegram_chat_id = int(chat_id)
        try:
            path = telegram_chat_path(self.agent_name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(str(int(chat_id)), encoding="utf-8")
        except OSError:
            pass

    def _telegram_mirror_chat_id(self) -> int | None:
        from marius.channels.telegram.config import load as load_tg_cfg

        cfg = load_tg_cfg()
        if not cfg or not cfg.enabled or cfg.agent_name != self.agent_name:
            return None
        if cfg.allowed_chats:
            return int(cfg.allowed_chats[0])
        if self.telegram_chat_id is not None:
            return self.telegram_chat_id
        if cfg.allowed_users:
            return int(cfg.allowed_users[0])
        return None

    def _mirror_visible_to_telegram(self, *, role: str, content: str, channel: str) -> None:
        if channel == "telegram":
            return
        text_content = str(content or "").strip()
        if role not in {"user", "assistant"} or not text_content:
            return
        chat_id = self._telegram_mirror_chat_id()
        if chat_id is None:
            return
        from marius.channels.telegram.config import load as load_tg_cfg
        from marius.channels.telegram.api import send_message

        cfg = load_tg_cfg()
        if not cfg or not cfg.token:
            return
        label = {
            "web": "Marius web",
            "cli": "Marius CLI",
            "routine": "Routine",
        }.get(channel, channel or "autre canal")
        speaker = "Vous" if role == "user" else "Marius"
        text = f"**{label} · {speaker}**\n\n{text_content}"
        ok = send_message(cfg.token, chat_id, text)
        log_event("telegram_mirror_sent", {
            "agent": self.agent_name,
            "channel": channel,
            "chat_id": chat_id,
            "role": role,
            "ok": ok,
        })

    def run_turn_for_telegram(self, text: str) -> str:
        """Exécute un tour depuis Telegram. Bloquant, sérialisé via turn_lock."""
        from marius.kernel.contracts import Message, Role
        text = text.strip()
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
            artifacts=self._native_image_artifacts(text),
        )
        from marius.kernel.runtime import TurnInput
        with self._turn_lock:
            try:
                self._publish_visible("user", text, channel="telegram")
                command_response = self._handle_builtin_command(text)
                if command_response is not None:
                    self._publish_visible("assistant", command_response, channel="telegram")
                    log_event("turn_done", {
                        "session_id": self.agent_name, "channel": "telegram",
                        "model": self.entry.model,
                        "tool_results": 0,
                        "assistant_preview": preview(command_response),
                        "command": text.split(maxsplit=1)[0].lower() if text else "",
                    })
                    return command_response

                text = self.resolve_skill_command(text)
                user_message.content = text
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
                if output.assistant_message is not None:
                    rendered = render_turn_output(
                        _without_content(output.assistant_message) if response else output.assistant_message,
                        tool_results=output.tool_results,
                        compaction_notice=output.compaction_notice,
                        surface=RenderSurface.TELEGRAM,
                    )
                    if response and rendered:
                        response = f"{response}\n\n{rendered}"
                    elif rendered:
                        response = rendered
                if response.strip():
                    self._publish_visible("assistant", response, channel="telegram")
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

    def new_conversation(
        self,
        *,
        clear_visible: bool = True,
        channel: str = "unknown",
        reason: str = "manual",
    ) -> None:
        """Réinitialise la session canonique runtime et, si demandé, le visible."""
        with self._turn_lock:
            previous_turns = len(self.session.state.turns)
            previous_metadata_keys = sorted(self.session.state.metadata.keys())
            self.session = SessionRuntime(
                session_id=self.agent_name,
                metadata={"provider": self.entry.name, "model": self.entry.model},
            )
            if clear_visible:
                _archive_and_clear_visible_history(self.agent_name)
                self._broadcast(VisibleResetEvent(channel=channel))
            log_event("conversation_reset", {
                "agent": self.agent_name,
                "session_id": self.agent_name,
                "channel": channel,
                "reason": reason,
                "clear_visible": clear_visible,
                "previous_turns": previous_turns,
                "previous_metadata_keys": previous_metadata_keys,
            })

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

    def _handle_builtin_command(self, text: str) -> str | None:
        if not text.startswith("/"):
            return None
        parts = text.split(maxsplit=1)
        cmd = parts[0].lower()
        arg = parts[1].strip() if len(parts) > 1 else ""

        if cmd in {"/new", "/stop"}:
            return None
        if cmd == "/help":
            return self._command_help()
        if cmd == "/remember":
            return self._command_remember(arg)
        if cmd == "/memories":
            return self._command_memories()
        if cmd == "/forget":
            return self._command_forget(arg)
        if cmd == "/doctor":
            return self._command_doctor()
        if cmd == "/dream":
            return self._command_dream()
        if cmd == "/context":
            return self._command_context()
        if cmd == "/compact":
            return self._command_compact()
        if cmd.lstrip("/") in self.skill_commands:
            return None
        return f"Je n’ai pas de commande `{cmd}` ici."

    def _command_help(self) -> str:
        rows = [
            ("/help", "Afficher les commandes"),
            ("/new", "Nouvelle conversation"),
            ("/stop", "Interrompre le tour en cours"),
            ("/remember <texte>", "Mémoriser un fait"),
            ("/memories", "Lister les souvenirs"),
            ("/forget <id>", "Supprimer un souvenir"),
            ("/doctor", "Diagnostic de l'installation"),
            ("/dream", "Consolider la mémoire"),
            ("/context", "Afficher l'état du contexte"),
            ("/compact", "Compacter le contexte court"),
        ]
        lines = ["# Commandes disponibles", ""]
        lines.extend(f"- `{name}` — {desc}" for name, desc in rows)
        if self.skill_commands:
            lines.extend(["", "## Commandes skills", ""])
            for command in self.skill_commands.values():
                lines.append(f"- `/{command.name}` — {command.description} [{command.skill_name}]")
        return "\n".join(lines)

    def _command_remember(self, text: str) -> str:
        if not text:
            return "Usage : `/remember <texte>`"
        memory_id = self.memory_store.add(text)
        return f"Souvenir #{memory_id} enregistré."

    def _command_memories(self) -> str:
        entries = self.memory_store.list(limit=30)
        if not entries:
            return "Aucun souvenir enregistré."
        lines = [f"# Souvenirs ({len(entries)})", ""]
        for entry in entries:
            tags = f" `{entry.tags}`" if entry.tags else ""
            scope = f" ({entry.scope})" if entry.scope != "global" else ""
            lines.append(f"- #{entry.id}{scope}{tags} — {entry.content}")
        return "\n".join(lines)

    def _command_forget(self, raw_id: str) -> str:
        if not raw_id.lstrip("#").isdigit():
            return "Usage : `/forget <id>`"
        memory_id = int(raw_id.lstrip("#"))
        if self.memory_store.remove(memory_id):
            return f"Souvenir #{memory_id} supprimé."
        return f"Souvenir #{memory_id} introuvable."

    def _command_doctor(self) -> str:
        from marius.config.doctor import format_report_text, run_doctor
        report, _errors = format_report_text(run_doctor(self.agent_name))
        return f"```text\n{report.strip()}\n```"

    def _command_dream(self) -> str:
        from marius.tools.dreaming import make_dreaming_tools
        tools = make_dreaming_tools(
            memory_store=self.memory_store,
            entry=self.entry,
            active_skills=self.active_skills or None,
            project_root=self.workspace,
        )
        result = tools["dreaming_run"].handler({})
        return result.summary if result.ok else f"Dreaming échoué : {result.summary}"

    def _command_context(self) -> str:
        from marius.kernel.compaction import compaction_level, estimate_tokens_from_messages
        messages = self.session.internal_messages(include_summary=True, include_tool_results=True)
        tokens = estimate_tokens_from_messages(messages)
        window = resolve_context_window(self.entry.model, "static")
        level = compaction_level(tokens, CompactionConfig(context_window_tokens=window))
        pct = (tokens / window * 100) if window else 0
        return (
            "# Contexte\n\n"
            f"- tours : {len(self.session.state.turns)}\n"
            f"- messages : {len(messages)}\n"
            f"- tokens estimés : {tokens:,} / {window:,} ({pct:.1f}%)\n"
            f"- niveau : `{level.value}`"
        )

    def _command_compact(self) -> str:
        with self._turn_lock:
            kept = self.orchestrator.compaction_config.keep_recent_turns
            before = len(self.session.state.turns)
            if before > kept:
                self.session.state.turns = self.session.state.turns[-kept:]
            after = len(self.session.state.turns)
        _append_visible_compaction_boundary(
            self.agent_name,
            kept_turns=after,
            removed_turns=before - after,
        )
        return f"Compaction effectuée : {before - after} tour(s) supprimé(s), {after} conservé(s)."

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
        if not hasattr(self, "_turn_context"):
            self._turn_context = threading.local()
        conn = getattr(self._turn_context, "conn", None) or self._conn
        channel = str(getattr(self._turn_context, "channel", "") or "")
        if conn is None:
            return False
        import uuid
        req_id = uuid.uuid4().hex[:8]
        ev: threading.Event = threading.Event()
        result: list[bool] = [False]
        self._pending_perms[req_id] = (ev, result)
        request = PermissionRequestEvent(
            tool_name=tool_name,
            reason=reason,
            request_id=req_id,
        )
        try:
            if channel == "task":
                self._broadcast(request)
            else:
                self._send(conn, request)
            ev.wait(timeout=_PERMISSION_TIMEOUT_SECONDS)
        finally:
            self._pending_perms.pop(req_id, None)
        return result[0]

    def _record_approval(self, event: dict[str, Any]) -> None:
        self.approval_store.record(
            fingerprint=str(event.get("fingerprint") or ""),
            tool_name=str(event.get("tool_name") or ""),
            arguments=dict(event.get("arguments") or {}),
            reason=str(event.get("reason") or ""),
            mode=str(event.get("mode") or ""),
            cwd=str(event.get("cwd") or ""),
            approved=bool(event.get("approved", False)),
        )

    # ── helpers ───────────────────────────────────────────────────────────────

    def _send(self, conn: socket.socket, event: Any) -> None:
        with self._send_lock:
            try:
                conn.sendall(encode(event))
            except OSError:
                pass

    def _broadcast(self, event: Any) -> None:
        if not hasattr(self, "_connections_lock"):
            return
        with self._connections_lock:
            connections = list(getattr(self, "_connections", set()))
        for conn in connections:
            self._send(conn, event)

    def _publish_visible(
        self,
        role: str,
        content: str,
        *,
        channel: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        text = str(content or "").strip()
        if role not in {"user", "assistant"} or not text:
            return
        sanitized_tools = _sanitize_visible_tools(tools)
        created_at = _append_visible_history(
            self.agent_name,
            role,
            text,
            channel=channel,
            tools=sanitized_tools,
        )
        if created_at is None:
            return
        self._broadcast(VisibleEvent(
            role=role,
            content=text,
            channel=channel,
            created_at=created_at,
            tools=sanitized_tools,
        ))
        self._mirror_visible_to_telegram(role=role, content=text, channel=channel)

    def _native_image_artifacts(self, text: str) -> list[Artifact]:
        if self._has_local_vision_tool():
            return []
        return _attached_image_artifacts(text, self.workspace)

    def _has_local_vision_tool(self) -> bool:
        try:
            return any(tool.name == "vision" for tool in self.tool_router.definitions())
        except Exception:
            return False

    def _build_tool_router(
        self,
        enabled_tools: list[str] | None,
        guard: PermissionGuard,
        cwd: Path,
        entry: ProviderEntry | None = None,
        permission_mode: str = "limited",
        allowed_roots_provider: Callable[[], tuple[Path, ...]] | None = None,
    ) -> ToolRouter:
        entries = build_tool_entries(
            enabled_tools,
            self.memory_store,
            cwd,
            entry=entry,
            active_skills=self.active_skills or None,
            agent_name=self.agent_name,
            reminders_store=self.reminders_store,
            get_reminder_chat_id=lambda: self.telegram_chat_id,
            permission_mode=permission_mode,
            allowed_roots=self.allowed_roots,
            allowed_roots_provider=allowed_roots_provider,
        )

        return ToolRouter(entries, guard=guard)

    def _ensure_search_backend(self, enabled_tools: list[str] | None) -> None:
        if enabled_tools is not None and "web_search" not in enabled_tools:
            return
        from marius.services.searxng import ensure_searxng_started
        result = ensure_searxng_started()
        log_event("searxng_startup", {
            "agent": self.agent_name,
            "ok": result.ok,
            "status": result.status,
            "url": result.url,
            "compose_file": result.compose_file,
            "detail": result.detail,
        })

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
        lock_file = lock_path(self.agent_name).open("w", encoding="utf-8")
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            sys.stderr.write(f"Gateway '{self.agent_name}' déjà actif.\n")
            lock_file.close()
            return

        lock_file.seek(0)
        lock_file.truncate()
        lock_file.write(str(os.getpid()))
        lock_file.flush()

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
        server_sock.listen(16)

        try:
            while True:
                conn, _ = server_sock.accept()
                threading.Thread(
                    target=self._handle_connection_thread,
                    args=(conn,),
                    daemon=True,
                    name=f"gateway-client-{self.agent_name}",
                ).start()
        finally:
            server_sock.close()
            if sock_path.exists():
                sock_path.unlink()
            pf = pid_path(self.agent_name)
            if pf.exists():
                pf.unlink()
            try:
                lock_file.close()
            except OSError:
                pass
            self._write_corpus()

    def _handle_connection_thread(self, conn: socket.socket) -> None:
        with self._connections_lock:
            self._connections.add(conn)
        self._conn = conn
        try:
            self._handle_connection(conn)
        except Exception:
            pass
        finally:
            with self._connections_lock:
                self._connections.discard(conn)
            if self._conn is conn:
                self._conn = None
            try:
                conn.close()
            except OSError:
                pass

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
                    self.orchestrator.cancel_current_provider()
                elif cmd == "/new":
                    channel = str(event.get("channel") or "cli")
                    if turn_thread is not None and turn_thread.is_alive():
                        if stop_event:
                            stop_event.set()
                        self.orchestrator.cancel_current_provider()
                    self.new_conversation(
                        clear_visible=True,
                        channel=channel,
                        reason="command",
                    )
                    self._send(conn, StatusEvent(message="Nouvelle conversation démarrée."))
                    self._mirror_visible_to_telegram(
                        role="assistant",
                        content="Nouvelle conversation démarrée.",
                        channel=channel,
                    )

            elif etype == "input":
                if turn_thread and turn_thread.is_alive():
                    log_event("turn_input_rejected_busy", {
                        "session_id": self.agent_name,
                        "agent": self.agent_name,
                        "user_preview": preview(str(event.get("text", ""))),
                    })
                    self._send(conn, ErrorEvent(message="Un tour est déjà en cours. Attends la fin ou utilise Stop."))
                    self._send(conn, DoneEvent())
                    continue
                stop_event = threading.Event()
                text = event.get("text", "")
                channel = str(event.get("channel") or "cli")
                turn_thread = threading.Thread(
                    target=self._run_turn,
                    args=(conn, text, stop_event, channel),
                    daemon=True,
                )
                turn_thread.start()

    def _run_turn(
        self, conn: socket.socket, text: str, stop_event: threading.Event, channel: str = "web"
    ) -> None:
        text = text.strip()
        visible_response_parts: list[str] = []
        visible_tools: list[dict[str, Any]] = []
        user_message = Message(
            role=Role.USER,
            content=text,
            created_at=datetime.now(timezone.utc),
            artifacts=self._native_image_artifacts(text),
        )
        log_event("turn_start", {
            "session_id": self.agent_name,
            "agent": self.agent_name,
            "cwd": str(self.workspace),
            "provider": self.entry.name,
            "provider_kind": self.entry.provider,
            "model": self.entry.model,
            "channel": channel,
            "user_preview": preview(text),
        })
        sent_text_delta = False

        def on_text_delta(delta: str) -> None:
            nonlocal sent_text_delta
            if stop_event.is_set():
                raise KeyboardInterrupt
            sent_text_delta = True
            visible_response_parts.append(delta)
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
            visible_tools.append({
                "id": call.id,
                "name": call.name,
                "target": preview(target, limit=200),
                "ok": None,
                "summary": "",
                "error": "",
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
            trace = next((t for t in reversed(visible_tools) if t.get("id") == call.id), None)
            if trace is None:
                trace = {
                    "id": call.id,
                    "name": call.name,
                    "target": "",
                    "ok": None,
                    "summary": "",
                    "error": "",
                }
                visible_tools.append(trace)
            trace["ok"] = bool(result.ok)
            trace["summary"] = preview(result.summary, limit=300)
            trace["error"] = preview(result.error or "", limit=300)
            self._send(conn, ToolResultEvent(name=call.name, ok=result.ok))

        try:
            with self._turn_lock:
                if not hasattr(self, "_turn_context"):
                    self._turn_context = threading.local()
                self._turn_context.conn = conn
                self._turn_context.channel = channel
                publish_user_visible = channel not in {"routine", "task"}
                if publish_user_visible:
                    self._publish_visible("user", text, channel=channel)
                command_response = self._handle_builtin_command(text)
                if command_response is not None:
                    self._send(conn, DeltaEvent(text=command_response))
                    self._publish_visible("assistant", command_response, channel=channel)
                    log_event("turn_done", {
                        "session_id": self.agent_name,
                        "agent": self.agent_name,
                        "provider": self.entry.name,
                        "provider_kind": self.entry.provider,
                        "model": self.entry.model,
                        "tool_results": 0,
                        "assistant_preview": preview(command_response),
                        "command": text.split(maxsplit=1)[0].lower() if text else "",
                    })
                    return

                text = self.resolve_skill_command(text)
                user_message.content = text
                system_prompt = self._system_prompt_for_session()
                if stop_event.is_set():
                    raise KeyboardInterrupt
                output = self.orchestrator.run_turn(
                    TurnInput(
                        session=self.session,
                        user_message=user_message,
                        system_prompt=system_prompt,
                    ),
                    on_text_delta=on_text_delta,
                    on_tool_start=on_tool_start,
                    on_tool_result=on_tool_result,
                    is_cancelled=stop_event.is_set,
                )
                if output.assistant_message is not None:
                    content = output.assistant_message.content
                    rendered = render_turn_output(
                        _without_content(output.assistant_message) if sent_text_delta else output.assistant_message,
                        tool_results=output.tool_results,
                        compaction_notice=output.compaction_notice,
                        surface=RenderSurface.WEB,
                    )
                    if rendered:
                        prefix = "\n\n" if sent_text_delta else ""
                        self._send(conn, DeltaEvent(text=f"{prefix}{rendered}"))
                        visible_response_parts.append(f"{prefix}{rendered}")
                    visible_response = "".join(visible_response_parts).strip() or content
                    if visible_response.strip():
                        self._publish_visible(
                            "assistant",
                            visible_response,
                            channel=channel,
                            tools=visible_tools,
                        )
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
            if getattr(self._turn_context, "conn", None) is conn:
                self._turn_context.conn = None
                self._turn_context.channel = ""
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

    last_boundary = -1
    for index, item in enumerate(history):
        if not isinstance(item, dict):
            continue
        metadata = item.get("metadata")
        if isinstance(metadata, dict) and metadata.get("kind") == "compaction_boundary":
            last_boundary = index

    pairs: list[tuple[str, str]] = []
    pending_user: str | None = None
    for item in history[last_boundary + 1:]:
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


def _attached_image_artifacts(text: str, workspace: Path) -> list[Artifact]:
    uploads_root = (workspace / "uploads").expanduser().resolve(strict=False)
    artifacts: list[Artifact] = []
    seen: set[Path] = set()
    for match in _ATTACHMENT_RE.finditer(text or ""):
        raw_path = match.group(1).strip()
        if not raw_path:
            continue
        try:
            path = Path(raw_path).expanduser().resolve(strict=False)
        except (OSError, RuntimeError):
            continue
        if path in seen:
            continue
        if not _is_under_path(path, uploads_root):
            continue
        mime_type = mimetypes.guess_type(path.name)[0] or ""
        if mime_type not in _NATIVE_IMAGE_MIME_TYPES:
            continue
        if not path.is_file():
            continue
        seen.add(path)
        artifacts.append(Artifact(
            type=ArtifactType.IMAGE,
            path=str(path),
            data={"mime_type": mime_type, "source": "user_attachment"},
        ))
    return artifacts


def _is_under_path(path: Path, root: Path) -> bool:
    try:
        return path == root or root in path.parents
    except RuntimeError:
        return False


def _sanitize_visible_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for tool in tools or []:
        if not isinstance(tool, dict):
            continue
        name = str(tool.get("name") or "").strip()
        if not name:
            continue
        rows.append({
            "name": name,
            "target": preview(str(tool.get("target") or ""), limit=200),
            "ok": bool(tool.get("ok")) if tool.get("ok") is not None else None,
            "summary": preview(str(tool.get("summary") or ""), limit=300),
            "error": preview(str(tool.get("error") or ""), limit=300),
        })
    return rows


def _append_visible_history(
    agent_name: str,
    role: str,
    content: str,
    *,
    channel: str,
    tools: list[dict[str, Any]] | None = None,
) -> str | None:
    text = str(content or "").strip()
    if role not in {"user", "assistant"} or not text:
        return None
    path = web_history_path(agent_name)
    created_at = datetime.now(timezone.utc).isoformat()
    sanitized_tools = _sanitize_visible_tools(tools) if role == "assistant" else []

    def append(messages: list[dict[str, Any]]) -> None:
        entry: dict[str, Any] = {
            "role": role,
            "content": text,
            "created_at": created_at,
            "channel": channel,
        }
        if sanitized_tools:
            entry["tools"] = sanitized_tools
        messages.append(entry)

    _mutate_visible_history(
        path,
        append,
    )
    return created_at


def _append_visible_compaction_boundary(
    agent_name: str,
    *,
    kept_turns: int,
    removed_turns: int,
) -> None:
    path = web_history_path(agent_name)
    _mutate_visible_history(
        path,
        lambda messages: messages.append({
            "role": "system",
            "content": "",
            "created_at": datetime.now(timezone.utc).isoformat(),
            "metadata": {
                "kind": "compaction_boundary",
                "kept_turns": kept_turns,
                "removed_turns": removed_turns,
            },
        }),
    )


def _archive_and_clear_visible_history(agent_name: str) -> None:
    history_path = web_history_path(agent_name)
    conversations = FileVisibleConversationStore(web_conversations_dir(agent_name))

    def mutate(messages: list[dict[str, Any]]) -> None:
        conversations.archive(messages, agent=agent_name)
        messages.clear()

    _mutate_visible_history(history_path, mutate)


def _mutate_visible_history(path: Path, mutate: Any) -> None:
    lock_path = path.with_suffix(path.suffix + ".lock")
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock_file:
        fcntl.flock(lock_file, fcntl.LOCK_EX)
        try:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                raw = []
            messages = raw if isinstance(raw, list) else []
            mutate(messages)
            path.write_text(json.dumps(messages, ensure_ascii=False), encoding="utf-8")
        finally:
            fcntl.flock(lock_file, fcntl.LOCK_UN)


def _without_content(message: Message) -> Message:
    return replace(message, content="")
