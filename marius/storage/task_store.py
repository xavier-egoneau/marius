"""Store de tâches global (~/.marius/tasks.json).

Une tâche est une unité de travail standalone :
  - backlog   : idée / plan non encore assigné
  - queued    : décidé, consommé par le scheduler dès que possible
                (ou à l'heure prévue si scheduled_for est renseigné)
  - running   : en cours d'exécution par un agent
  - failed    : lancement impossible après retry
  - done      : terminé
  - paused    : suspendu / mis en attente

Tâches récurrentes (recurring=True) :
  - elles apparaissent dans l'onglet Routines, pas le Task Board
  - leur prompt est envoyé au gateway de l'agent selon la cadence

Tâches système (system=True) :
  - créées automatiquement par le gateway (dreaming)
  - exécutées directement par le scheduler, pas via socket
"""

from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_MARIUS_HOME = Path.home() / ".marius"


@dataclass
class Task:
    id: str
    title: str
    prompt: str       = ""           # source unique de cadrage/exécution (vide = title)
    status: str       = "backlog"    # backlog|queued|running|failed|done|paused
    priority: str     = "med"        # high|med|low
    agent: str        = ""           # nom de l'agent assigné
    project_path: str = ""           # chemin absolu du dossier projet
    recurring: bool   = False        # True → apparaît dans Routines
    cadence: str      = ""           # "1d", "08:00", "Nh", "Nd", "weekly"
    scheduled_for: str = ""          # ISO datetime pour exécution unique future
    system: bool      = False        # True → tâche système (dreaming)
    next_run_at: str  = ""           # ISO datetime — prochain run planifié (géré par TaskScheduler)
    last_run: str     = ""           # ISO datetime du dernier run
    last_error: str   = ""           # message d'erreur du dernier run
    attempts: int     = 0            # tentatives d'envoi queue
    max_attempts: int = 5            # échec final après N tentatives
    next_attempt_at: str = ""        # ISO datetime — prochain retry queue
    locked_at: str    = ""           # ISO datetime — lock d'envoi en cours
    locked_by: str    = ""           # identifiant du runner qui a pris le lock
    created_at: str   = ""
    updated_at: str   = ""
    events: list[dict] = field(default_factory=list)


_FIELDS = set(Task.__dataclass_fields__)
_LEGACY_MAP = {"project": "project_path"}


def _initial_next_run_at(recurring: bool, cadence: str) -> str:
    if not recurring or not str(cadence or "").strip():
        return ""
    try:
        from marius.kernel.scheduler import next_run_from_cadence
        return next_run_from_cadence(str(cadence)).isoformat()
    except Exception:
        return ""


def _should_refresh_next_run(
    data: dict[str, Any],
    *,
    old_recurring: bool,
    new_recurring: bool,
    old_cadence: str,
    new_cadence: str,
    next_run_at: str,
) -> bool:
    recurring_changed = bool(old_recurring) != bool(new_recurring)
    cadence_changed = str(old_cadence or "") != str(new_cadence or "")
    if recurring_changed or cadence_changed:
        return True
    if ("cadence" in data or "recurring" in data) and not _next_run_matches_cadence(next_run_at, new_cadence):
        return True
    return "next_run_at" not in data and ("cadence" in data or "recurring" in data)


def _next_run_matches_cadence(next_run_at: str, cadence: str) -> bool:
    raw = str(cadence or "").strip()
    parts = raw.split(":", 1)
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1].isdigit():
        return True
    try:
        hour = int(parts[0])
        minute = int(parts[1])
        dt = datetime.fromisoformat(str(next_run_at or "").replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return False
    local = dt.astimezone()
    return local.hour == hour and local.minute == minute


def _normalize_status(value: Any) -> str:
    status = str(value or "backlog")
    if status in {"review", "archived"}:
        return "done"
    return status


class TaskStore:
    def __init__(self, path: Path | None = None) -> None:
        self._path = Path(path) if path else _MARIUS_HOME / "tasks.json"
        self._lock = threading.RLock()

    def load(self) -> list[Task]:
        import fcntl
        if not self._path.exists():
            return []
        lock_path = self._path.with_suffix(".lock")
        try:
            with open(lock_path, "w") as lf:
                fcntl.flock(lf, fcntl.LOCK_SH)
                try:
                    data = json.loads(self._path.read_text(encoding="utf-8"))
                finally:
                    fcntl.flock(lf, fcntl.LOCK_UN)
            tasks = []
            for t in data.get("tasks", []):
                for old, new in _LEGACY_MAP.items():
                    if old in t and new not in t:
                        t[new] = t[old]
                if t.get("description") and not t.get("prompt"):
                    t["prompt"] = t["description"]
                t["status"] = _normalize_status(t.get("status", "backlog"))
                kwargs = {k: v for k, v in t.items() if k in _FIELDS}
                tasks.append(Task(**kwargs))
            return tasks
        except (json.JSONDecodeError, TypeError, OSError):
            return []

    def save(self, tasks: list[Task]) -> None:
        import fcntl
        self._path.parent.mkdir(parents=True, exist_ok=True)
        lock_path = self._path.with_suffix(".lock")
        with self._lock:
            with open(lock_path, "w") as lf:
                fcntl.flock(lf, fcntl.LOCK_EX)
                try:
                    self._path.write_text(
                        json.dumps({"tasks": [asdict(t) for t in tasks]}, indent=2, ensure_ascii=False),
                        encoding="utf-8",
                    )
                finally:
                    fcntl.flock(lf, fcntl.LOCK_UN)

    def create(self, data: dict[str, Any]) -> Task:
        now = datetime.now(timezone.utc).isoformat()
        recurring = bool(data.get("recurring", False))
        cadence = str(data.get("cadence", ""))
        task = Task(
            id=data.get("id") or f"t_{uuid.uuid4().hex[:8]}",
            title=str(data.get("title", "")).strip(),
            prompt=str(data.get("prompt", "")),
            status=_normalize_status(data.get("status", "backlog")),
            priority=str(data.get("priority", "med")),
            agent=str(data.get("agent", "")),
            project_path=str(data.get("project_path") or data.get("project", "")),
            recurring=recurring,
            cadence=cadence,
            scheduled_for=str(data.get("scheduled_for", "")),
            system=bool(data.get("system", False)),
            next_run_at=str(data.get("next_run_at", "")) or _initial_next_run_at(recurring, cadence),
            attempts=int(data.get("attempts", 0) or 0),
            max_attempts=int(data.get("max_attempts", 5) or 5),
            next_attempt_at=str(data.get("next_attempt_at", "")),
            locked_at=str(data.get("locked_at", "")),
            locked_by=str(data.get("locked_by", "")),
            created_at=now,
            updated_at=now,
            events=list(data.get("events", [])) or [{"kind": "created", "at": now}],
        )
        with self._lock:
            tasks = self.load()
            tasks.append(task)
            self.save(tasks)
        return task

    def upsert(self, data: dict[str, Any]) -> Task:
        """Crée ou met à jour une tâche par id."""
        with self._lock:
            tasks = self.load()
            task_id = data.get("id")
            existing = next((t for t in tasks if t.id == task_id), None) if task_id else None
            if existing is None:
                return self.create(data)
            old_recurring = existing.recurring
            old_cadence = existing.cadence
            for key, val in data.items():
                mapped = _LEGACY_MAP.get(key, key)
                if mapped in _FIELDS and mapped not in ("id", "created_at", "events"):
                    if mapped == "status":
                        val = _normalize_status(val)
                    setattr(existing, mapped, val)
            if _should_refresh_next_run(
                data,
                old_recurring=old_recurring,
                new_recurring=existing.recurring,
                old_cadence=old_cadence,
                new_cadence=existing.cadence,
                next_run_at=existing.next_run_at,
            ):
                existing.next_run_at = _initial_next_run_at(existing.recurring, existing.cadence)
            existing.updated_at = datetime.now(timezone.utc).isoformat()
            self.save(tasks)
            return existing

    def update(self, task_id: str, data: dict[str, Any]) -> Task | None:
        with self._lock:
            tasks = self.load()
            task = next((t for t in tasks if t.id == task_id), None)
            if task is None:
                return None
            now = datetime.now(timezone.utc).isoformat()
            old_status = task.status
            old_recurring = task.recurring
            old_cadence = task.cadence
            allowed = _FIELDS - {"id", "created_at", "events"}
            for key, val in data.items():
                mapped = _LEGACY_MAP.get(key, key)
                if mapped in allowed:
                    if mapped == "status":
                        val = _normalize_status(val)
                    setattr(task, mapped, val)
            if _should_refresh_next_run(
                data,
                old_recurring=old_recurring,
                new_recurring=task.recurring,
                old_cadence=old_cadence,
                new_cadence=task.cadence,
                next_run_at=task.next_run_at,
            ):
                task.next_run_at = _initial_next_run_at(task.recurring, task.cadence)
            task.updated_at = now
            if task.status != old_status:
                task.events.append({"kind": "status_changed", "at": now,
                                    "from": old_status, "to": task.status})
                if old_status == "running" and task.status != "running":
                    task.locked_at = ""
                    task.locked_by = ""
                    if task.status in {"backlog", "queued", "paused"}:
                        task.events.append({
                            "kind": "cancel_requested",
                            "at": now,
                            "from": old_status,
                            "to": task.status,
                        })
            self.save(tasks)
            return task

    def add_event(self, task_id: str, event: dict[str, Any]) -> Task | None:
        with self._lock:
            tasks = self.load()
            task = next((t for t in tasks if t.id == task_id), None)
            if task is None:
                return None
            event.setdefault("at", datetime.now(timezone.utc).isoformat())
            task.events.append(event)
            task.updated_at = event["at"]
            self.save(tasks)
            return task

    def delete(self, task_id: str) -> bool:
        with self._lock:
            tasks = self.load()
            filtered = [t for t in tasks if t.id != task_id]
            if len(filtered) == len(tasks):
                return False
            self.save(filtered)
            return True

    def list_all(
        self,
        project: str | None = None,
        agent: str | None = None,
        include_archived: bool = False,
        recurring_only: bool = False,
        non_recurring_only: bool = False,
    ) -> list[Task]:
        tasks = self.load()
        if recurring_only:
            tasks = [t for t in tasks if t.recurring]
        if non_recurring_only:
            tasks = [t for t in tasks if not t.recurring]
        if project:
            tasks = [t for t in tasks if t.project_path == project]
        if agent:
            tasks = [t for t in tasks if t.agent == agent]
        order = {"running": 0, "queued": 1, "backlog": 2, "paused": 3, "failed": 4, "done": 5}
        tasks.sort(key=lambda t: order.get(t.status, 9))
        return tasks

    def recover_interrupted_running(self, agent: str, *, reason: str = "gateway restarted before task completion") -> list[Task]:
        """Récupère les tâches restées `running` pour un agent redémarré.

        Le board ne possède pas encore de run durable capable de survivre à un
        restart du gateway. Si le process meurt avant que l'agent appelle
        `task_update`, la tâche resterait sinon bloquée visuellement en cours.

        Les tâches uniques sont marquées `failed` afin d'éviter un second envoi
        automatique après un redémarrage. Les routines peuvent revenir en
        `queued`, car leur prochain tir reste porté par `next_run_at`.
        """
        agent_name = str(agent or "").strip()
        if not agent_name:
            return []
        recovered: list[Task] = []
        with self._lock:
            tasks = self.load()
            now = datetime.now(timezone.utc).isoformat()
            for task in tasks:
                if task.agent != agent_name or task.status != "running":
                    continue
                next_status = "queued" if task.recurring else "failed"
                task.status = next_status
                task.last_error = reason[:300]
                task.locked_at = ""
                task.locked_by = ""
                task.updated_at = now
                task.events.append({"kind": "status_changed", "at": now, "from": "running", "to": next_status})
                task.events.append({"kind": "interrupted", "at": now, "agent": agent_name, "reason": reason[:300]})
                recovered.append(task)
            if recovered:
                self.save(tasks)
        return recovered


def seed_agent_system_tasks(agent_name: str, tools: list[str]) -> None:
    """Crée les routines système de dreaming pour un agent si elles n'existent pas encore.

    Idempotent — peut être appelé à la création ou à la mise à jour d'un agent.
    """
    tool_set = set(tools or [])
    has_dreaming = "dreaming_run" in tool_set

    if not has_dreaming:
        return

    store = TaskStore()
    existing_ids = {t.id for t in store.load()}
    seeds: list[dict] = []

    if has_dreaming:
        tid = f"sys_dream_{agent_name}"
        if tid not in existing_ids:
            seeds.append({
                "id":        tid,
                "title":     "Dreaming",
                "prompt":    "/dream",
                "recurring": True,
                "cadence":   "02:00",
                "agent":     agent_name,
                "system":    True,
                "status":    "queued",
                "priority":  "low",
            })

    for seed in seeds:
        try:
            store.create(seed)
        except Exception:
            pass
