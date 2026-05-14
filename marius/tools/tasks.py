"""Outils task board — CRUD sur le task store global."""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from marius.kernel.tool_router import ToolEntry, ToolResult


def make_task_tools() -> "dict[str, ToolEntry]":
    from marius.kernel.tool_router import ToolEntry, ToolDefinition, ToolResult
    from marius.storage.task_store import TaskStore

    def task_create(arguments: dict[str, Any]) -> "ToolResult":
        prompt = str(arguments.get("prompt", ""))
        data = {
            "title":        str(arguments.get("title", "")).strip(),
            "prompt":       prompt,
            "status":       str(arguments.get("status", "backlog")),
            "priority":     str(arguments.get("priority", "med")),
            "agent":        str(arguments.get("agent", "")),
            "project_path": str(arguments.get("project_path", "")),
            "recurring":    bool(arguments.get("recurring", False)),
            "cadence":      str(arguments.get("cadence", "")),
            "scheduled_for": str(arguments.get("scheduled_for", "")),
        }
        if not data["title"]:
            return ToolResult(tool_call_id="", ok=False, summary="title is required", error="missing_title")
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
        allowed = {"title", "prompt", "status", "priority", "agent", "last_error",
                   "project_path", "recurring", "cadence", "scheduled_for"}
        data = {k: v for k, v in arguments.items() if k in allowed}
        for field in ("title", "status", "priority", "agent", "project_path"):
            if field in data and isinstance(data[field], str) and not data[field].strip():
                del data[field]
        task = TaskStore().update(task_id, data)
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
                    "Crée une nouvelle tâche dans le task board (kanban). "
                    "Utilise ce tool quand l'utilisateur veut ajouter quelque chose à son backlog, "
                    "noter une idée, planifier un travail, ou créer une routine."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "title":        {"type": "string", "description": "Titre court et clair de la tâche."},
                        "prompt":       {"type": "string", "description": "Source unique de cadrage et d'exécution envoyée au gateway. Mets ici le plan complet, les critères, le contexte et le hors scope."},
                        "status":       {"type": "string", "enum": ["backlog", "queued", "running", "failed", "done"], "description": "Statut initial. Défaut : backlog."},
                        "priority":     {"type": "string", "enum": ["high", "med", "low"], "description": "Priorité. Défaut : med."},
                        "agent":        {"type": "string", "description": "Nom de l'agent assigné."},
                        "project_path": {"type": "string", "description": "Chemin absolu du projet concerné."},
                        "recurring":    {"type": "boolean", "description": "True si c'est une routine récurrente (apparaît dans l'onglet Routines)."},
                        "cadence":      {"type": "string", "description": "Cadence si recurring=true. Ex: '08:00', 'daily', '4h'."},
                        "scheduled_for":{"type": "string", "description": "Datetime ISO pour lancement unique futur."},
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
                    "Liste les tâches du task board. Permet de filtrer par statut, agent ou projet. "
                    "Utilise ce tool pour voir ce qui est en cours, en backlog, ou terminé."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "status":       {"type": "string", "enum": ["backlog", "queued", "running", "failed", "done"], "description": "Filtrer par statut."},
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
                    "Omettre les champs que tu ne modifies pas ; les valeurs vides pour title/status/"
                    "priority/agent/project_path sont ignorées pour éviter d'effacer le board par accident."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "id":           {"type": "string", "description": "ID de la tâche (ex: t_a1b2c3d4)."},
                        "title":        {"type": "string"},
                        "prompt":       {"type": "string", "description": "Source unique de cadrage et d'exécution de la task."},
                        "status":       {"type": "string", "enum": ["backlog", "queued", "running", "failed", "done", "archived"]},
                        "priority":     {"type": "string", "enum": ["high", "med", "low"]},
                        "agent":        {"type": "string"},
                        "project_path": {"type": "string"},
                        "last_error":   {"type": "string", "description": "Résumé court si la task passe en failed."},
                        "recurring":    {"type": "boolean"},
                        "cadence":      {"type": "string"},
                        "scheduled_for":{"type": "string", "description": "Datetime ISO pour lancement unique futur."},
                    },
                    "required": ["id"],
                },
            ),
            handler=task_update,
        ),
    }


TASK_CREATE, TASK_LIST, TASK_UPDATE = None, None, None  # lazy — loaded via make_task_tools()
