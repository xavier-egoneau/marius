"""Outils task board — CRUD sur le task store global."""

from __future__ import annotations

import re
from dataclasses import asdict
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from marius.kernel.tool_router import ToolEntry, ToolResult


_NEW_PROJECT_MARKERS = {"nouveau", "new", "__new__", "__new_project__"}


def _is_new_project_marker(value: str) -> bool:
    return str(value or "").strip().lower() in _NEW_PROJECT_MARKERS


def make_task_tools(*, default_agent: str = "") -> "dict[str, ToolEntry]":
    from marius.kernel.tool_router import ToolEntry, ToolDefinition, ToolResult
    from marius.storage.task_store import TaskStore

    def _normalize_routine_cadence(value: Any) -> tuple[str, str | None]:
        raw = str(value or "").strip().lower().replace(" ", "")
        if not raw:
            return "", "cadence is required for recurring tasks"
        if raw in {"manual", "off", "disabled"}:
            return "", "manual/off/disabled cadence does not create an active routine; use status=paused instead"
        if raw == "daily":
            return "", "daily is ambiguous; use HH:MM for a daily fixed local time, or 1d for a 24h interval"
        if raw in {"hourly", "weekly"}:
            return raw, None
        if re.fullmatch(r"\d{1,2}h\d{2}", raw):
            raw = raw.replace("h", ":", 1)
        if re.fullmatch(r"\d{1,2}:\d{2}", raw):
            from marius.kernel.scheduler import validate_hhmm
            try:
                return validate_hhmm(raw), None
            except ValueError as exc:
                return "", str(exc)
        if re.fullmatch(r"\d+[mhd]", raw):
            value_int = int(raw[:-1])
            if value_int <= 0:
                return "", "cadence interval must be greater than zero"
            return f"{value_int}{raw[-1]}", None
        return "", "unsupported cadence; use HH:MM, Nm, Nh, Nd, hourly, or weekly"

    def _valid_iso_datetime(value: Any) -> bool:
        raw = str(value or "").strip()
        if not raw:
            return True
        try:
            datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return False
        return True

    def task_create(arguments: dict[str, Any]) -> "ToolResult":
        prompt = str(arguments.get("prompt", ""))
        recurring = bool(arguments.get("recurring", False))
        scheduled_for = str(arguments.get("scheduled_for", ""))
        project_path = str(arguments.get("project_path", ""))
        default_status = (
            "queued"
            if recurring or scheduled_for.strip() or _is_new_project_marker(project_path)
            else "backlog"
        )
        data = {
            "title":        str(arguments.get("title", "")).strip(),
            "prompt":       prompt,
            "status":       str(arguments.get("status", default_status)),
            "priority":     str(arguments.get("priority", "med")),
            "agent":        str(arguments.get("agent") or default_agent),
            "project_path": project_path,
            "recurring":    recurring,
            "cadence":      str(arguments.get("cadence", "")),
            "scheduled_for": scheduled_for,
        }
        if not data["title"]:
            return ToolResult(tool_call_id="", ok=False, summary="title is required", error="missing_title")
        if recurring:
            cadence, error = _normalize_routine_cadence(data["cadence"])
            if error:
                return ToolResult(tool_call_id="", ok=False, summary=error, error="invalid_cadence")
            data["cadence"] = cadence
            data["scheduled_for"] = ""
        elif scheduled_for and not _valid_iso_datetime(scheduled_for):
            return ToolResult(tool_call_id="", ok=False, summary="scheduled_for must be an ISO datetime", error="invalid_scheduled_for")
        task = TaskStore().create(data)
        return ToolResult(
            tool_call_id="", ok=True,
            summary=f"Task créée : [{task.status.upper()}] {task.title} (id: {task.id})",
            data=asdict(task),
        )

    def task_list(arguments: dict[str, Any]) -> "ToolResult":
        store = TaskStore()
        status_filter  = str(arguments.get("status", "")).strip() or None
        agent_filter   = str(arguments.get("agent", "")).strip() or None
        project_filter = str(arguments.get("project_path", "")).strip() or None
        recurring_only = bool(arguments.get("recurring", False))

        tasks = store.list_all(
            agent=agent_filter,
            project=project_filter,
            recurring_only=recurring_only,
            non_recurring_only=not recurring_only,
        )
        if status_filter:
            tasks = [t for t in tasks if t.status == status_filter]

        lines = [f"[{t.status.upper()}] [{t.priority}] {t.title} (id:{t.id})"
                 + (f" — {t.agent}" if t.agent else "")
                 for t in tasks]
        summary = f"{len(tasks)} task(s)" + (f" filtrées par status={status_filter}" if status_filter else "")
        return ToolResult(
            tool_call_id="", ok=True,
            summary=summary + ("\n" + "\n".join(lines) if lines else ""),
            data={"tasks": [asdict(t) for t in tasks]},
        )

    def task_update(arguments: dict[str, Any]) -> "ToolResult":
        task_id = str(arguments.get("id", "")).strip()
        if not task_id:
            return ToolResult(tool_call_id="", ok=False, summary="id is required", error="missing_id")
        store = TaskStore()
        existing = next((t for t in store.load() if t.id == task_id), None)
        if existing is None:
            return ToolResult(tool_call_id="", ok=False, summary=f"Task '{task_id}' not found", error="not_found")
        allowed = {"title", "prompt", "status", "priority", "agent", "last_error",
                   "project_path", "recurring", "cadence", "scheduled_for"}
        data = {k: v for k, v in arguments.items() if k in allowed}
        for field in ("title", "prompt", "status", "priority", "agent", "project_path"):
            if field in data and isinstance(data[field], str) and not data[field].strip():
                del data[field]
        next_recurring = bool(data.get("recurring", existing.recurring))
        if next_recurring and ("recurring" in data or "cadence" in data):
            cadence, error = _normalize_routine_cadence(data.get("cadence", existing.cadence))
            if error:
                return ToolResult(tool_call_id="", ok=False, summary=error, error="invalid_cadence")
            data["cadence"] = cadence
            data["scheduled_for"] = ""
        if not next_recurring and data.get("scheduled_for") and not _valid_iso_datetime(data["scheduled_for"]):
            return ToolResult(tool_call_id="", ok=False, summary="scheduled_for must be an ISO datetime", error="invalid_scheduled_for")
        task = store.update(task_id, data)
        if task is None:
            return ToolResult(tool_call_id="", ok=False, summary=f"Task '{task_id}' not found", error="not_found")
        return ToolResult(
            tool_call_id="", ok=True,
            summary=f"Task mise à jour : [{task.status.upper()}] {task.title}",
            data=asdict(task),
        )

    return {
        "task_create": ToolEntry(
            definition=ToolDefinition(
                name="task_create",
                description=(
                    "Crée une nouvelle entrée suivie dans le Task Board ou une routine. "
                    "Utilise ce tool seulement si l'utilisateur demande explicitement de créer, noter, "
                    "suivre, planifier, mettre au backlog, programmer une tâche, créer une routine, "
                    "ou créer un nouveau projet. "
                    "Si l'utilisateur demande naturellement de créer un nouveau projet, crée une task "
                    "Kanban assignée à l'agent courant, avec project_path='nouveau' et status='queued' "
                    "sauf demande contraire. Si le nom, l'emplacement ou l'idée du projet manquent et "
                    "ne peuvent pas être déduits prudemment, pose les questions avant de créer la task. "
                    "Si l'utilisateur demande une routine, une tâche récurrente, un cron, ou une exécution "
                    "répétée (tous les jours, chaque semaine, toutes les X heures/minutes), crée une routine "
                    "avec recurring=true et une cadence explicite ; elle apparaîtra dans l'onglet Routines, "
                    "pas dans le Task Board. Une routine active doit toujours avoir un déclencheur clair. "
                    "Formats de cadence acceptés : HH:MM pour une heure locale quotidienne fixe (ex: 10:00), "
                    "Nm/Nh/Nd pour un intervalle en minutes/heures/jours (ex: 30m, 4h, 1d), hourly, weekly. "
                    "N'utilise pas d'expression cron type '0 10 * * *'. N'utilise pas daily : choisis HH:MM "
                    "si l'utilisateur veut une heure fixe, ou 1d si l'utilisateur veut un intervalle de 24h. "
                    "weekly signifie un intervalle de 7 jours depuis la création, pas un jour précis de la "
                    "semaine. Si l'utilisateur dit seulement 'tous les jours', 'chaque semaine' ou "
                    "'régulièrement' sans heure ni intervalle exploitable, demande la cadence souhaitée avant "
                    "de créer la routine. "
                    "Pour une tâche unique future, utilise recurring=false, scheduled_for en ISO 8601 et "
                    "status=queued ; scheduled_for ne s'applique pas aux routines. "
                    "Ne crée pas de task pour une demande conversationnelle immédiate comme "
                    "'fais-moi une veille IA' : exécute-la directement si possible."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "title":        {"type": "string", "description": "Titre court et clair de la tâche."},
                        "prompt":       {"type": "string", "description": "Source unique de cadrage et d'exécution envoyée au gateway. Mets ici le plan complet, les critères, le contexte et le hors scope."},
                        "status":       {"type": "string", "enum": ["backlog", "queued", "running", "failed", "done", "paused"], "description": "Statut initial. Défaut : backlog pour une task simple, queued pour une routine ou une task planifiée. Utilise paused pour créer une routine inactive."},
                        "priority":     {"type": "string", "enum": ["high", "med", "low"], "description": "Priorité. Défaut : med."},
                        "agent":        {"type": "string", "description": "Nom de l'agent assigné. Optionnel : par défaut, l'agent courant qui crée la task."},
                        "project_path": {"type": "string", "description": "Chemin absolu du projet concerné. Utilise 'nouveau' pour une task de création de nouveau projet ; la task créera le dossier puis mettra à jour ce champ avec le chemin réel."},
                        "recurring":    {"type": "boolean", "description": "True si c'est une routine récurrente ou un cron demandé par l'utilisateur ; false pour une task unique."},
                        "cadence":      {"type": "string", "description": "Déclencheur obligatoire si recurring=true. Formats acceptés : 'HH:MM' heure locale quotidienne fixe, 'Nm', 'Nh', 'Nd', 'hourly', 'weekly'. Pas de cron brut, pas de 'daily'."},
                        "scheduled_for":{"type": "string", "description": "Datetime ISO 8601 pour lancement unique futur avec recurring=false. Recommandé avec timezone, ex: 2026-05-15T10:00:00+02:00 ou UTC Z."},
                    },
                    "required": ["title"],
                },
            ),
            handler=task_create,
        ),
        "task_list": ToolEntry(
            definition=ToolDefinition(
                name="task_list",
                description=(
                    "Liste les tâches uniques du Task Board par défaut. Permet de filtrer par statut, "
                    "agent ou projet. Avec recurring=true, liste les routines au lieu des tasks uniques."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "status":       {"type": "string", "enum": ["backlog", "queued", "running", "failed", "done", "paused"], "description": "Filtrer par statut."},
                        "agent":        {"type": "string", "description": "Filtrer par agent assigné."},
                        "project_path": {"type": "string", "description": "Filtrer par projet."},
                        "recurring":    {"type": "boolean", "description": "Si true, retourne uniquement les routines."},
                    },
                },
            ),
            handler=task_list,
        ),
        "task_update": ToolEntry(
            definition=ToolDefinition(
                name="task_update",
                description=(
                    "Met à jour une tâche existante (statut, priorité, prompt/plan, assignation…). "
                    "Utilise task_list d'abord pour trouver l'id si tu ne l'as pas. "
                    "Le cadrage d'une task doit être écrit dans `prompt`, source unique envoyée au gateway. "
                    "Omettre les champs que tu ne modifies pas ; les valeurs vides pour title/prompt/"
                    "status/priority/agent/project_path sont ignorées pour éviter d'effacer le board par accident."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "id":           {"type": "string", "description": "ID de la tâche (ex: t_a1b2c3d4)."},
                        "title":        {"type": "string"},
                        "prompt":       {"type": "string", "description": "Source unique de cadrage et d'exécution de la task."},
                        "status":       {"type": "string", "enum": ["backlog", "queued", "running", "failed", "done", "paused"]},
                        "priority":     {"type": "string", "enum": ["high", "med", "low"]},
                        "agent":        {"type": "string"},
                        "project_path": {"type": "string"},
                        "last_error":   {"type": "string", "description": "Résumé court si la task passe en failed."},
                        "recurring":    {"type": "boolean"},
                        "cadence":      {"type": "string", "description": "Déclencheur de routine. Formats acceptés : 'HH:MM', 'Nm', 'Nh', 'Nd', 'hourly', 'weekly'."},
                        "scheduled_for":{"type": "string", "description": "Datetime ISO 8601 pour lancement unique futur avec recurring=false."},
                    },
                    "required": ["id"],
                },
            ),
            handler=task_update,
        ),
    }


TASK_CREATE, TASK_LIST, TASK_UPDATE = None, None, None  # lazy — loaded via make_task_tools()
