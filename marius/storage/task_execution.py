"""Messages d'exécution des tâches uniques du Task Board."""

from __future__ import annotations

from typing import Any

_NEW_PROJECT_MARKERS = {"nouveau", "new", "__new__", "__new_project__"}


def task_execution_message(task: Any) -> str:
    """Construit le prompt interne qui demande à l'agent d'exécuter une task unique."""
    body = (getattr(task, "prompt", "") or "").strip()
    if not body:
        body = str(getattr(task, "title", "") or "")
    project_path = str(getattr(task, "project_path", "") or "").strip()
    if project_path and project_path.lower() not in _NEW_PROJECT_MARKERS:
        body = f"Projet cible: {project_path}\n\n{body}"
    task_id = str(getattr(task, "id", "") or "").strip()
    if not task_id:
        return body
    instructions = (
        "[Task Board]\n"
        f"Task id: {task_id}\n"
        "Exécute uniquement la task ci-dessous. Quand le travail est livré, "
        f"appelle l'outil task_update avec id={task_id} et status=\"done\". "
        "Si tu ne peux pas livrer après avoir réellement essayé, appelle "
        f"task_update avec id={task_id}, status=\"failed\" et last_error. "
        "Ne crée pas de nouvelle task."
    )
    if body.startswith("/"):
        command, _, arg = body.partition(" ")
        prompt = f"{instructions}\n\n[Prompt]\n{arg.strip()}" if arg.strip() else instructions
        return f"{command} {prompt}".strip()
    return f"{instructions}\n\n[Prompt]\n{body}"

