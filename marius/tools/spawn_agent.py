"""Outil spawn_agent — parallélisation de tâches via workers délégués.

Permet à l'agent orchestrateur de spawner des workers bornés pour exécuter
des tâches indépendantes en parallèle.

Contraintes :
  - Max 5 workers par appel
  - Workers ne peuvent pas spawner d'autres workers (depth = 1)
  - Timeout par défaut 5min, max 15min
  - Rapport structuré retourné pour chaque worker
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
from typing import Any

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.kernel.worker import (
    DEFAULT_MAX_ITERATIONS,
    DEFAULT_MAX_SECONDS,
    MAX_WORKERS_PER_CALL,
    WorkerTask,
    run_worker,
)


def make_spawn_agent_tool(
    entry: Any,                     # ProviderEntry
    parent_tool_entries: list[Any], # ToolEntry — filtrées avant passage
    *,
    permission_mode: str = "limited",
    cwd: Path,
) -> ToolEntry:
    """Fabrique l'outil spawn_agent en fermant sur le contexte du parent.

    Les workers reçoivent tous les outils du parent SAUF spawn_agent
    (depth = 1, pas de récursion).
    """
    worker_tool_entries = [
        t for t in parent_tool_entries
        if t.definition.name != "spawn_agent"
    ]

    def _handler(arguments: dict[str, Any]) -> ToolResult:
        raw_workers = arguments.get("workers", [])
        if not isinstance(raw_workers, list) or not raw_workers:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Argument `workers` manquant ou vide.",
                error="missing_arg:workers",
            )

        # Limite stricte
        capped = raw_workers[:MAX_WORKERS_PER_CALL]
        skipped = len(raw_workers) - len(capped)

        max_seconds = min(
            int(arguments.get("max_seconds", DEFAULT_MAX_SECONDS)),
            900,
        )

        tasks = [_parse_task(w) for w in capped]
        results: dict[int, Any] = {}

        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            future_map = {
                executor.submit(
                    run_worker,
                    task,
                    entry=entry,
                    tool_entries=worker_tool_entries,
                    permission_mode=permission_mode,
                    cwd=cwd,
                    max_seconds=max_seconds,
                    max_iterations=DEFAULT_MAX_ITERATIONS,
                ): idx
                for idx, task in enumerate(tasks)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = asdict(future.result())
                except Exception as exc:
                    results[idx] = {
                        "task": tasks[idx].task,
                        "status": "failed",
                        "summary": "",
                        "error": str(exc),
                        "elapsed_seconds": 0.0,
                    }

        ordered = [results[i] for i in range(len(tasks))]
        completed = sum(1 for r in ordered if r["status"] == "completed")
        blocked    = sum(1 for r in ordered if r["status"] == "blocked")
        arb        = sum(1 for r in ordered if r["status"] == "needs_arbitration")

        lines = [f"{completed}/{len(tasks)} worker(s) terminé(s)."]
        if blocked:
            lines.append(f"{blocked} bloqué(s).")
        if arb:
            lines.append(f"{arb} demande(s) d'arbitrage.")
        if skipped:
            lines.append(f"{skipped} worker(s) ignoré(s) (limite {MAX_WORKERS_PER_CALL}).")

        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="\n".join(lines),
            data={
                "workers": ordered,
                "skipped": skipped,
            },
        )

    return ToolEntry(
        definition=ToolDefinition(
            name="spawn_agent",
            description=(
                "Spawner des agents workers pour exécuter des tâches indépendantes en parallèle. "
                "Chaque worker reçoit un contexte minimal (task + fichiers pertinents) et retourne "
                "un rapport structuré. Utilise quand le plan contient des tâches [parallélisable]. "
                "Max 5 workers par appel. Les workers ne peuvent pas spawner d'autres workers. "
                "Si un worker retourne status=needs_arbitration, spawne de nouveaux workers "
                "pour les sous-tâches identifiées dans son rapport."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "workers": {
                        "type": "array",
                        "description": "Liste des tâches à exécuter en parallèle (max 5).",
                        "items": {
                            "type": "object",
                            "properties": {
                                "task": {
                                    "type": "string",
                                    "description": "Description précise de la mission du worker.",
                                },
                                "context_summary": {
                                    "type": "string",
                                    "description": "Contexte minimal nécessaire (quelques phrases max).",
                                },
                                "relevant_files": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Chemins des fichiers à lire (relatifs au CWD).",
                                },
                                "write_paths": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": "Chemins où le worker est autorisé à écrire.",
                                },
                                "expected_output": {
                                    "type": "string",
                                    "description": "Format ou contenu attendu en sortie.",
                                },
                            },
                            "required": ["task"],
                        },
                    },
                    "max_seconds": {
                        "type": "integer",
                        "description": f"Timeout par worker en secondes (défaut {DEFAULT_MAX_SECONDS}, max 900).",
                    },
                },
                "required": ["workers"],
            },
        ),
        handler=_handler,
    )


def _parse_task(raw: dict[str, Any]) -> WorkerTask:
    return WorkerTask(
        task=str(raw.get("task", "")),
        context_summary=str(raw.get("context_summary", "")),
        relevant_files=[str(f) for f in raw.get("relevant_files", [])],
        write_paths=[str(p) for p in raw.get("write_paths", [])],
        expected_output=str(raw.get("expected_output", "")),
    )
