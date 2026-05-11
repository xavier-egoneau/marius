"""Agent de travail délégué (worker).

Un worker est une exécution bornée, isolée, sans état durable.
Il reçoit une mission précise, travaille avec un contexte minimal,
et retourne un rapport structuré à l'orchestrateur.

Contraintes :
  - Pas de spawning récursif (spawn_agent retiré du registry)
  - Pas de mémoire partagée avec le parent
  - Timeout dur + limite d'itérations d'outils
  - Rapport structuré obligatoire
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .compaction import CompactionConfig
from .contracts import Message, Role, ToolCall, ToolResult
from .runtime import RuntimeOrchestrator, TurnInput
from .session import SessionRuntime
from .tool_router import ToolRouter

# ── constantes ────────────────────────────────────────────────────────────────

MAX_WORKERS_PER_CALL   = 5
MAX_FILE_CONTEXT_CHARS = 18_000
DEFAULT_MAX_SECONDS    = 300    # 5 minutes
MAX_SECONDS            = 900    # 15 minutes
DEFAULT_MAX_ITERATIONS = 12


# ── types ─────────────────────────────────────────────────────────────────────


@dataclass
class WorkerTask:
    task: str
    context_summary: str = ""
    relevant_files: list[str] = field(default_factory=list)
    write_paths: list[str] = field(default_factory=list)
    expected_output: str = ""


@dataclass
class WorkerResult:
    task: str
    status: str          # completed | blocked | needs_arbitration | failed | timeout
    summary: str
    changed_files: list[str] = field(default_factory=list)
    blocker: str = ""
    verification: str = ""
    error: str = ""
    elapsed_seconds: float = 0.0


# ── runner principal ──────────────────────────────────────────────────────────


def run_worker(
    worker_task: WorkerTask,
    *,
    entry: Any,                  # ProviderEntry — évite import circulaire
    tool_entries: list[Any],     # ToolEntry filtrées (sans spawn_agent)
    permission_mode: str = "limited",
    cwd: Path,
    max_seconds: int = DEFAULT_MAX_SECONDS,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> WorkerResult:
    """Exécute un worker isolé. Bloquant — à lancer dans un thread."""
    max_seconds = min(max_seconds, MAX_SECONDS)
    started = time.monotonic()

    # Contexte fichiers
    file_context = _load_relevant_files(worker_task.relevant_files, cwd)
    system_prompt = _build_system_prompt(worker_task, file_context)

    # Garde de permissions — auto-deny (pas d'interactivité pour un worker)
    from .permission_guard import PermissionGuard
    guard = PermissionGuard(
        mode=permission_mode,
        cwd=cwd,
        on_ask=lambda *_: False,
    )
    tool_router = ToolRouter(tool_entries, guard=guard)

    from marius.adapters.http_provider import make_adapter
    adapter = make_adapter(entry)
    orchestrator = RuntimeOrchestrator(
        provider=adapter,
        tool_router=tool_router,
        compaction_config=CompactionConfig(context_window_tokens=32_000),
    )

    session = SessionRuntime(
        session_id=f"worker-{id(worker_task)}",
        metadata={"kind": "worker"},
    )
    user_message = Message(
        role=Role.USER,
        content="Accomplis la mission. Termine par le rapport structuré obligatoire.",
        created_at=datetime.now(timezone.utc),
    )

    # Timeout via cancel_event
    cancel_event = threading.Event()
    timer = threading.Timer(max_seconds, cancel_event.set)
    timer.daemon = True
    timer.start()

    # Limite d'itérations d'outils
    iterations = [0]
    full_text: list[str] = []

    def on_text_delta(delta: str) -> None:
        if cancel_event.is_set():
            raise KeyboardInterrupt
        full_text.append(delta)

    def on_tool_start(call: ToolCall) -> None:
        if cancel_event.is_set():
            raise KeyboardInterrupt
        iterations[0] += 1
        if iterations[0] >= max_iterations:
            cancel_event.set()

    def on_tool_result(call: ToolCall, result: ToolResult) -> None:
        pass

    timed_out = False
    error_msg = ""
    try:
        orchestrator.run_turn(
            TurnInput(
                session=session,
                user_message=user_message,
                system_prompt=system_prompt,
            ),
            on_text_delta=on_text_delta,
            on_tool_start=on_tool_start,
            on_tool_result=on_tool_result,
        )
    except KeyboardInterrupt:
        timed_out = cancel_event.is_set() and timer.is_alive() is False or iterations[0] >= max_iterations
        timed_out = cancel_event.is_set()
    except Exception as exc:
        error_msg = str(exc)
    finally:
        timer.cancel()

    elapsed = time.monotonic() - started
    response_text = "".join(full_text)

    if timed_out:
        return WorkerResult(
            task=worker_task.task,
            status="timeout",
            summary=f"Worker interrompu après {elapsed:.0f}s (limite : {max_seconds}s).",
            elapsed_seconds=elapsed,
        )

    if error_msg:
        return WorkerResult(
            task=worker_task.task,
            status="failed",
            summary="Erreur provider.",
            error=error_msg,
            elapsed_seconds=elapsed,
        )

    report = _parse_report(response_text)
    status = report.get("status", "completed")
    if status not in ("completed", "blocked", "needs_arbitration"):
        status = "completed"

    changed_raw = report.get("changed_files", "none")
    changed_files = (
        []
        if changed_raw.strip().lower() in ("none", "")
        else [f.strip() for f in changed_raw.split(",")]
    )

    return WorkerResult(
        task=worker_task.task,
        status=status,
        summary=report.get("summary", response_text.strip()[:500]),
        changed_files=changed_files,
        blocker=report.get("blocker", ""),
        verification=report.get("verification", ""),
        elapsed_seconds=elapsed,
    )


# ── system prompt ─────────────────────────────────────────────────────────────


def _build_system_prompt(task: WorkerTask, file_context: str) -> str:
    parts: list[str] = []

    parts.append(
        "Tu es un agent de travail délégué. L'agent parent est l'orchestrateur.\n"
        "Accomplis exactement la mission assignée — rien de plus, rien de moins.\n"
        "\n"
        "Contraintes strictes :\n"
        "- Ne spawne pas d'autres agents.\n"
        "- Ne modifie pas le plan global — tu n'en as pas connaissance.\n"
        "- Si tu rencontres un blocage, une ambiguïté ou un conflit : "
        "arrête et rapporte avec status=blocked.\n"
        "- Si tu as besoin que l'orchestrateur spawne d'autres workers : "
        "arrête avec status=needs_arbitration et décris le besoin dans blocker.\n"
        "- Écris uniquement dans les chemins autorisés.\n"
        "- Ton rapport final est obligatoire et doit respecter le format ci-dessous."
    )

    parts.append(f"## Mission\n{task.task}")

    if task.context_summary:
        parts.append(f"## Contexte\n{task.context_summary}")

    if task.write_paths:
        parts.append("## Chemins d'écriture autorisés\n" + "\n".join(task.write_paths))

    if task.expected_output:
        parts.append(f"## Format de sortie attendu\n{task.expected_output}")

    if file_context:
        parts.append(f"## Fichiers pertinents\n{file_context}")

    parts.append(
        "## Rapport obligatoire\n"
        "Termine TOUJOURS par ce bloc exact :\n"
        "```\n"
        "status: completed | blocked | needs_arbitration\n"
        "summary: <résumé du travail effectué>\n"
        "changed_files: <fichiers modifiés séparés par virgules> | none\n"
        "verification: <tests lancés ou vérification> | not_run: <raison>\n"
        "blocker: <description du blocage ou besoin de workers> | none\n"
        "```"
    )

    return "\n\n".join(parts)


# ── helpers ───────────────────────────────────────────────────────────────────


def _load_relevant_files(paths: list[str], cwd: Path) -> str:
    """Charge et injecte les fichiers pertinents (max MAX_FILE_CONTEXT_CHARS)."""
    if not paths:
        return ""
    parts: list[str] = []
    total = 0
    for path_str in paths:
        path = Path(path_str)
        if not path.is_absolute():
            path = (cwd / path_str).resolve()
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            parts.append(f"### {path_str}\n[fichier introuvable]")
            continue
        remaining = MAX_FILE_CONTEXT_CHARS - total
        if len(content) > remaining:
            content = content[:remaining] + "\n[...tronqué]"
        parts.append(f"### {path_str}\n```\n{content}\n```")
        total += len(content)
        if total >= MAX_FILE_CONTEXT_CHARS:
            parts.append("[Limite de contexte atteinte — fichiers suivants ignorés]")
            break
    return "\n\n".join(parts)


_REPORT_FIELDS = ("status", "summary", "changed_files", "verification", "blocker")


def _parse_report(text: str) -> dict[str, str]:
    """Extrait les champs du rapport structuré de la réponse du worker."""
    report: dict[str, str] = {}
    for line in reversed(text.splitlines()):   # le rapport est à la fin
        line = line.strip().lstrip("`")
        for field in _REPORT_FIELDS:
            if line.lower().startswith(f"{field}:"):
                report.setdefault(field, line.split(":", 1)[1].strip())
    return report
