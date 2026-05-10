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
        from marius.kernel.scheduler import JobStore, Scheduler, ensure_jobs
        from marius.gateway.workspace import jobs_path

        store = JobStore(jobs_path(self.agent_name))
        ensure_jobs(
            store,
            dream_time=getattr(agent_config, "dream_time", ""),
            daily_time=getattr(agent_config, "daily_time", ""),
        )

        handlers: dict[str, Any] = {}
        if getattr(agent_config, "dream_time", ""):
            handlers["dreaming"] = self._run_scheduled_dream
        if getattr(agent_config, "daily_time", ""):
            handlers["daily"] = self._run_scheduled_daily

        if not handlers:
            return

        self._scheduler = Scheduler(store, handlers)
        t = threading.Thread(target=self._scheduler.run_forever, daemon=True)
        t.start()

    def _run_scheduled_dream(self) -> None:
        from marius.dreaming.engine import run_dreaming
        run_dreaming(
            memory_store=self.memory_store,
            entry=self.entry,
            active_skills=self.active_skills or None,
            project_root=self.workspace,
        )

    def _run_scheduled_daily(self) -> None:
        from marius.dreaming.engine import run_daily
        from marius.gateway.workspace import daily_cache_path

        briefing = run_daily(
            memory_store=self.memory_store,
            entry=self.entry,
            active_skills=self.active_skills or None,
            project_root=self.workspace,
        )
        try:
            daily_cache_path(self.agent_name).write_text(briefing, encoding="utf-8")
        except OSError:
            pass
        self._push_daily_telegram(briefing)

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

    def _push_daily_telegram(self, briefing: str) -> None:
        chat_id = self._get_chat_id()
        if chat_id is not None:
            self._send_telegram(chat_id, briefing)

    def _send_telegram(self, chat_id: int, text: str) -> None:
        try:
            from marius.channels.telegram.config import load as load_tg_cfg
            from marius.channels.telegram.api import send_message
            cfg = load_tg_cfg()
            if cfg and cfg.enabled:
                send_message(cfg.token, chat_id, text)
        except Exception:
            pass
