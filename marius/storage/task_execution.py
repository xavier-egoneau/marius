"""Messages d'exécution des tâches uniques du Task Board."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_NEW_PROJECT_MARKERS = {"nouveau", "new", "__new__", "__new_project__"}
_DEFAULT_PROJECTS_ROOT = Path.home() / "Documents" / "projets"


def task_execution_message(task: Any) -> str:
    """Construit le prompt interne qui demande à l'agent d'exécuter une task unique."""
    body = (getattr(task, "prompt", "") or "").strip()
    if not body:
        body = str(getattr(task, "title", "") or "")
    project_path = str(getattr(task, "project_path", "") or "").strip()
    if project_path and project_path.lower() in _NEW_PROJECT_MARKERS:
        new_project_path = str(getattr(task, "_new_project_path", "") or "").strip()
        target_line = (
            f"Chemin cible proposé: {new_project_path}"
            if new_project_path
            else f"Racine projets par défaut: {_DEFAULT_PROJECTS_ROOT}"
        )
        body = (
            "[Nouveau projet]\n"
            "Cette task commence volontairement sans projet actif réel. "
            "Crée d'abord le dossier du nouveau projet avec les outils filesystem, "
            "en demandant/attendant l'autorisation si le gardien la requiert. "
            "Si la task demande seulement de créer le projet, ne change pas le projet actif global. "
            "Appelle `task_update` sur cette task pour remplacer project_path='nouveau' "
            "par le chemin absolu réel. Si la task demande ensuite de travailler dans ce nouveau projet, "
            "appelle alors `project_set_active` sur ce dossier avant de poursuivre.\n"
            f"{target_line}\n\n"
            f"{body}"
        )
    elif project_path:
        body = (
            "[Projet de la task]\n"
            f"Projet cible: {project_path}\n"
            "Pour cette task, ce dossier est le projet actif d'exécution. "
            "Commence par appeler `project_set_active` sur ce chemin si le contexte actif "
            "ne correspond pas déjà, puis travaille dans ce projet sauf instruction explicite contraire.\n\n"
            f"{body}"
        )
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
