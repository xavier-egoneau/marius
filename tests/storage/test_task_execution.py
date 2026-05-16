from __future__ import annotations

from marius.storage.task_execution import task_execution_message
from marius.storage.task_store import Task


def test_task_execution_message_forces_task_project_context() -> None:
    task = Task(
        id="t_123",
        title="Implémente",
        prompt="fais le changement",
        project_path="/tmp/demo",
    )

    message = task_execution_message(task)

    assert "[Projet de la task]" in message
    assert "Projet cible: /tmp/demo" in message
    assert "appeler `project_set_active`" in message


def test_task_execution_message_describes_new_project_flow() -> None:
    task = Task(
        id="t_123",
        title="Créer projet toto",
        project_path="nouveau",
    )
    setattr(task, "_new_project_path", "/tmp/projets/toto")

    message = task_execution_message(task)

    assert "[Nouveau projet]" in message
    assert "Chemin cible proposé: /tmp/projets/toto" in message
    assert "sans projet actif réel" in message
    assert "Crée d'abord le dossier" in message
    assert "ne change pas le projet actif global" in message
    assert "remplacer project_path='nouveau'" in message
    assert "Si la task demande ensuite de travailler" in message
    assert "appelle alors `project_set_active`" in message
