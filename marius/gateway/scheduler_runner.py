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
from marius.storage.watch_store import WatchStore
from marius.tools.watch import WatchSummarizer, make_watch_tools, should_notify_topic

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
        watch_store: WatchStore | None = None,
        watch_search_handler: Callable[[dict[str, Any]], Any] | None = None,
        watch_summarizer: WatchSummarizer | None = None,
    ) -> None:
        self.agent_name     = agent_name
        self.workspace      = workspace
        self.memory_store   = memory_store
        self.entry          = entry
        self.active_skills  = active_skills
        self.reminders_store = reminders_store
        self.watch_store    = watch_store if watch_store is not None else WatchStore()
        self.watch_search_handler = watch_search_handler
        self.watch_summarizer = watch_summarizer
        self._get_chat_id   = get_telegram_chat_id
        self._scheduler     = None

        if getattr(agent_config, "scheduler_enabled", False):
            self._start_scheduler(agent_config)

        self._start_reminders_thread()

    # ── scheduler dream / daily ───────────────────────────────────────────────

    def _start_scheduler(self, agent_config: Any) -> None:
        from marius.kernel.scheduler import JobStore, Scheduler, cadence_to_seconds, ensure_jobs, ensure_watch_jobs
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

        def sync_watch_jobs() -> None:
            watch_topics = self.watch_store.list_topics(include_disabled=False)
            ensure_watch_jobs(store, watch_topics)
            for name in [name for name in handlers if name.startswith("watch:")]:
                del handlers[name]
            for topic in watch_topics:
                if cadence_to_seconds(str(getattr(topic, "cadence", "") or "manual")) is not None:
                    handlers[f"watch:{topic.id}"] = lambda topic_id=topic.id: self._run_scheduled_watch(topic_id)

        sync_watch_jobs()

        self._scheduler = Scheduler(store, handlers, before_tick=sync_watch_jobs)
        t = threading.Thread(target=self._scheduler.run_forever, daemon=True)
        t.start()

    def _run_scheduled_dream(self) -> None:
        from marius.tools.dreaming import make_dreaming_tools
        tools = make_dreaming_tools(
            memory_store=self.memory_store,
            entry=self.entry,
            active_skills=self.active_skills or None,
            project_root=self.workspace,
            watch_dir=self.watch_store.root,
        )
        result = tools["dreaming_run"].handler({})
        log_event("dreaming_run", {
            "agent": self.agent_name,
            "ok": result.ok,
            "summary": result.summary,
        })

    def _run_scheduled_daily(self) -> None:
        from marius.gateway.workspace import daily_cache_path
        from marius.tools.dreaming import make_dreaming_tools

        tools = make_dreaming_tools(
            memory_store=self.memory_store,
            entry=self.entry,
            active_skills=self.active_skills or None,
            project_root=self.workspace,
            watch_dir=self.watch_store.root,
        )
        result = tools["daily_digest"].handler({})
        briefing = str(result.data.get("markdown") or result.summary)
        try:
            daily_cache_path(self.agent_name).write_text(briefing, encoding="utf-8")
        except OSError:
            pass
        log_event("daily_digest", {
            "agent": self.agent_name,
            "ok": result.ok,
            "summary": result.summary,
        })
        self._push_daily_telegram(briefing)

    def _run_scheduled_watch(self, topic_id: str) -> None:
        tools = make_watch_tools(
            store=self.watch_store,
            search_handler=self.watch_search_handler,
            summarizer=self.watch_summarizer,
        )
        result = tools["watch_run"].handler({"id": topic_id})
        log_event("watch_run", {
            "agent": self.agent_name,
            "topic_id": topic_id,
            "ok": result.ok,
            "summary": result.summary,
        })
        topic = self.watch_store.get(topic_id)
        reports = result.data.get("reports", []) if isinstance(result.data, dict) else []
        report_data = (reports[0].get("report") if reports and isinstance(reports[0], dict) else {}) or {}
        notify = topic is not None and should_notify_topic(topic, report_data)
        chat_id = self._get_chat_id()
        if notify and chat_id is not None and result.ok:
            self._send_telegram(chat_id, result.summary)

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
