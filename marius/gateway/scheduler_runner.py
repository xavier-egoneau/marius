"""Scheduling des tâches périodiques du gateway.

Encapsule dreaming, daily, et livraison des rappels dans une classe indépendante.
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


class GatewayScheduler:
    """Exécute dreaming/daily en cron et livre les rappels à l'heure."""

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
    ) -> None:
        self.agent_name     = agent_name
        self.workspace      = workspace
        self.memory_store   = memory_store
        self.entry          = entry
        self.active_skills  = active_skills
        self.reminders_store = reminders_store
        self._get_chat_id   = get_telegram_chat_id
        self._scheduler     = None

        if getattr(agent_config, "scheduler_enabled", False):
            self._start_scheduler(agent_config)

        self._start_reminders_thread()

    # ── scheduler dream / daily ───────────────────────────────────────────────

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
                    and (task.scheduled_for or task.next_attempt_at)
                    and task.id not in handlers
                ):
                    handlers[task.id] = lambda tid=task.id: self._run_user_task(tid)

        self._scheduler = TaskScheduler(handlers, before_tick=before_tick)
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
        from marius.storage.task_store import TaskStore
        from marius.gateway.workspace import socket_path
        from marius.gateway.protocol import InputEvent, encode

        ts = TaskStore()
        task = next((t for t in ts.load() if t.id == task_id), None)
        if task is None:
            return

        if task.recurring:
            prompt = task.prompt.strip() or task.title
        else:
            prompt = task.prompt.strip() or task.title
        agent  = task.agent or self.agent_name
        sock   = socket_path(agent)
        if not sock.exists():
            raise OSError(f"Gateway '{agent}' non actif.")

        try:
            conn = _socket.socket(_socket.AF_UNIX, _socket.SOCK_STREAM)
            conn.settimeout(5.0)
            conn.connect(str(sock))
            buf = b""
            while b"\n" not in buf:
                chunk = conn.recv(4096)
                if not chunk:
                    break
                buf += chunk
            conn.sendall(encode(InputEvent(text=prompt)))
            conn.close()
        except OSError:
            raise

        ts.add_event(task_id, {
            "kind": "launched",
            "agent": agent,
            "cmd":   prompt[:200],
        })
        log_event("task_scheduled_run", {
            "agent":   self.agent_name,
            "task_id": task_id,
            "prompt":  prompt[:100],
        })

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
