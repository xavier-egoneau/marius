"""Scheduling des tâches périodiques du gateway.

Encapsule le dreaming planifié et la livraison des rappels dans une classe indépendante.
GatewayServer en possède une instance et lui passe les ressources partagées
via injection — aucune référence inverse vers GatewayServer.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from marius.provider_config.contracts import ProviderEntry
from marius.storage.log_store import log_event
from marius.storage.memory_store import MemoryStore
from marius.storage.reminders_store import RemindersStore

_REMINDERS_POLL_SECONDS = 30.0
_TASK_SCHEDULER_POLL_SECONDS = 10.0


def _parse_iso_datetime(value: str):
    from datetime import datetime, timezone

    try:
        dt = datetime.fromisoformat(str(value or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.astimezone()
    return dt.astimezone(timezone.utc)


def _raise_if_task_cancelled(task_id: str, run_started: Any) -> None:
    from marius.kernel.scheduler import TaskRunCancelled
    from marius.storage.task_store import TaskStore

    task = next((t for t in TaskStore().load() if t.id == task_id), None)
    if task is None:
        raise TaskRunCancelled(f"task {task_id} disappeared during execution")

    for event in reversed(task.events):
        if event.get("kind") != "cancel_requested":
            continue
        event_at = _parse_iso_datetime(str(event.get("at", "")))
        if event_at is None or event_at < run_started:
            continue
        target = str(event.get("to") or task.status)
        raise TaskRunCancelled(f"task {task_id} moved to {target}")


class GatewayScheduler:
    """Exécute le dreaming en cron et livre les rappels à l'heure."""

    def __init__(
        self,
        agent_name: str,
        workspace: Path,
        memory_store: MemoryStore,
        entry: ProviderEntry,
        active_skills: list[str],
        agent_config: Any,
        reminders_store: RemindersStore,
        get_telegram_chat_id: Callable[[], int | None],
        permission_mode: str = "limited",
    ) -> None:
        self.agent_name     = agent_name
        self.workspace      = workspace
        self.memory_store   = memory_store
        self.entry          = entry
        self.active_skills  = active_skills
        self.reminders_store = reminders_store
        self._get_chat_id   = get_telegram_chat_id
        self._scheduler     = None
        self.permission_mode = permission_mode

        if getattr(agent_config, "scheduler_enabled", False):
            self._start_scheduler(agent_config)

        self._start_reminders_thread()

    # ── scheduler dreaming ────────────────────────────────────────────────────

    def _start_scheduler(self, agent_config: Any) -> None:
        from marius.kernel.scheduler import TaskScheduler

        enabled_tools = set(getattr(agent_config, "tools", []) or [])
        has_dreaming  = "dreaming_run" in enabled_tools

        self._seed_system_tasks(has_dreaming)

        handlers: dict[str, Any] = {}
        if has_dreaming:
            handlers[f"sys_dream_{self.agent_name}"] = self._run_scheduled_dream

        def before_tick() -> None:
            from marius.storage.task_store import TaskStore

            # ── user recurring tasks ───────────────────────────────────────
            for task in TaskStore().list_all(agent=self.agent_name, recurring_only=True):
                if not task.system and task.cadence and task.id not in handlers:
                    handlers[task.id] = lambda tid=task.id: self._run_user_task(tid)
            for task in TaskStore().list_all(agent=self.agent_name, non_recurring_only=True):
                if (
                    not task.system
                    and task.status == "queued"
                    and task.id not in handlers
                ):
                    handlers[task.id] = lambda tid=task.id: self._run_user_task(tid)

        self._scheduler = TaskScheduler(
            handlers,
            before_tick=before_tick,
            poll_seconds=_TASK_SCHEDULER_POLL_SECONDS,
        )
        t = threading.Thread(target=self._scheduler.run_forever, daemon=True)
        t.start()

    def _seed_system_tasks(
        self,
        has_dreaming: bool,
    ) -> None:
        """Crée les tâches système récurrentes dans task_store si elles n'existent pas."""
        from marius.storage.task_store import seed_agent_system_tasks

        tools: list[str] = []
        if has_dreaming:
            tools.append("dreaming_run")
        seed_agent_system_tasks(self.agent_name, tools)

    def _run_user_task(self, task_id: str) -> None:
        """Exécute une tâche utilisateur récurrente en envoyant son prompt au gateway."""
        import socket as _socket
        from datetime import datetime, timezone
        from marius.storage.task_store import TaskStore
        from marius.gateway.workspace import socket_path
        from marius.gateway.protocol import InputEvent, PermissionResponseEvent, decode, encode
        from marius.kernel.scheduler import TaskRunCancelled

        ts = TaskStore()
        task = next((t for t in ts.load() if t.id == task_id), None)
        if task is None:
            return

        if task.recurring:
            prompt = task.prompt.strip() or task.title
            channel = "routine"
        else:
            from marius.storage.task_execution import task_execution_message
            self._authorize_task_project_root(task)
            prompt = task_execution_message(task)
            channel = "task"
        agent  = task.agent or self.agent_name
        sock   = socket_path(agent)
        if not sock.exists():
            raise OSError(f"Gateway '{agent}' non actif.")

        run_started = _parse_iso_datetime(task.locked_at) or datetime.now(timezone.utc)

        conn = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
        try:
            conn.settimeout(5.0)
            conn.connect(str(sock))
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
            conn.sendall(encode(InputEvent(text=prompt, channel=channel)))
            conn.settimeout(0.5)
            while True:
                while b"\n" not in buf:
                    _raise_if_task_cancelled(task_id, run_started)
                    try:
                        chunk = conn.recv(4096)
                    except _socket.timeout:
                        continue
                    if not chunk:
                        raise OSError("gateway closed before routine completion")
                    buf += chunk
                raw, buf = buf.split(b"\n", 1)
                event = decode(raw.decode(errors="replace"))
                etype = event.get("type")
                if etype == "permission_request":
                    if channel == "routine":
                        conn.sendall(encode(PermissionResponseEvent(
                            request_id=str(event.get("request_id") or ""),
                            approved=False,
                        )))
                    else:
                        log_event("task_permission_request_forwarded", {
                            "agent": self.agent_name,
                            "task_id": task_id,
                            "tool": str(event.get("tool_name") or ""),
                            "reason": str(event.get("reason") or "")[:300],
                        })
                elif etype == "error":
                    raise RuntimeError(str(event.get("message") or "routine failed"))
                elif etype in {"done", "status"}:
                    break
        except TaskRunCancelled:
            raise
        except OSError:
            raise
        finally:
            try:
                conn.close()
            except OSError:
                pass

        ts.add_event(task_id, {
            "kind": "launched",
            "agent": agent,
            "cmd":   prompt[:200],
            "channel": channel,
        })
        log_event("task_scheduled_run", {
            "agent":   self.agent_name,
            "task_id": task_id,
            "prompt":  prompt[:100],
        })

    def _authorize_task_project_root(self, task: Any) -> None:
        """Ajoute le project_path d'une task unique à la zone autorisée du run."""
        raw_path = str(getattr(task, "project_path", "") or "").strip()
        if not raw_path or raw_path.lower() in {"nouveau", "new", "__new__", "__new_project__"}:
            return

        from marius.kernel.guardian_policy import (
            AllowExpansionReason,
            AllowExpansionRequest,
            AllowExpansionStatus,
            DefaultGuardianPolicy,
        )
        from marius.kernel.project_context import PermissionMode
        from marius.storage.allow_root_store import AllowRootStore

        try:
            mode = PermissionMode(str(getattr(self, "permission_mode", "limited") or "limited"))
        except ValueError:
            mode = PermissionMode.LIMITED

        workspace = Path(getattr(self, "workspace", Path.home() / ".marius" / "workspace" / self.agent_name))
        allow_store = AllowRootStore()
        roots = tuple(root.expanduser().resolve(strict=False) for root in allow_store.paths())
        requested_root = Path(raw_path).expanduser().resolve(strict=False)

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
                allow_store.add(root, reason="task_project_path")
            log_event("task_project_root_authorized", {
                "agent": self.agent_name,
                "task_id": getattr(task, "id", ""),
                "project_path": str(requested_root),
                "code": decision.code.value,
            })
            return
        if decision.status is AllowExpansionStatus.DENY:
            raise PermissionError(
                f"Project path not allowed for task: {requested_root} ({decision.code.value})"
            )

    def _run_scheduled_dream(self) -> None:
        from marius.tools.dreaming import make_dreaming_tools
        tools = make_dreaming_tools(
            memory_store=self.memory_store,
            entry=self.entry,
            active_skills=self.active_skills or None,
            project_root=self.workspace,
        )
        result = tools["dreaming_run"].handler({})
        log_event("dreaming_run", {
            "agent": self.agent_name,
            "ok": result.ok,
            "summary": result.summary,
        })

    # ── reminders ─────────────────────────────────────────────────────────────

    def _start_reminders_thread(self) -> None:
        stop = threading.Event()

        def _loop() -> None:
            while not stop.wait(_REMINDERS_POLL_SECONDS):
                try:
                    self._fire_due_reminders()
                except Exception:
                    pass

        threading.Thread(target=_loop, daemon=True, name="reminders-delivery").start()

    def _fire_due_reminders(self) -> None:
        for reminder in self.reminders_store.due():
            self.reminders_store.mark_fired(reminder.id)
            text = f"🔔 {reminder.text}"
            chat_id = reminder.chat_id or self._get_chat_id()
            if chat_id is not None:
                self._send_telegram(chat_id, text)
            log_event("reminder_fired", {
                "agent": self.agent_name,
                "reminder_id": reminder.id,
                "text": reminder.text,
            })

    # ── push Telegram ─────────────────────────────────────────────────────────

    def _send_telegram(self, chat_id: int, text: str) -> None:
        try:
            from marius.channels.telegram.config import load as load_tg_cfg
            from marius.channels.telegram.api import send_message
            cfg = load_tg_cfg()
            if cfg and cfg.enabled:
                send_message(cfg.token, chat_id, text)
        except Exception:
            pass
