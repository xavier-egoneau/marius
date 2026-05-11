"""Outil shell pour Marius.

Standalone : dépend uniquement de kernel/tool_router et kernel/contracts.
"""

from __future__ import annotations

import subprocess
from typing import Any

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_TIMEOUT_SECONDS = 30


def _run_bash(arguments: dict[str, Any]) -> ToolResult:
    command = arguments.get("command", "")
    cwd = arguments.get("cwd") or None

    if not command:
        return ToolResult(tool_call_id="", ok=False, summary="Argument `command` manquant.", error="missing_arg:command")

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SECONDS,
            cwd=cwd,
        )
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()

        if result.returncode == 0:
            summary = stdout or "(commande exécutée sans sortie)"
            return ToolResult(
                tool_call_id="",
                ok=True,
                summary=summary,
                data={"command": command, "returncode": result.returncode, "stderr": stderr},
            )
        else:
            summary = stderr or stdout or f"Commande échouée (code {result.returncode})"
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary=summary,
                data={"command": command, "returncode": result.returncode, "stdout": stdout},
                error=stderr,
            )

    except subprocess.TimeoutExpired:
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Timeout après {_TIMEOUT_SECONDS}s : {command}",
            error="timeout",
        )
    except Exception as exc:
        return ToolResult(tool_call_id="", ok=False, summary=str(exc), error=str(exc))


# ── entrée du registre ────────────────────────────────────────────────────────

RUN_BASH = ToolEntry(
    definition=ToolDefinition(
        name="run_bash",
        description="Exécute une commande shell et retourne stdout/stderr.",
        parameters={
            "type": "object",
            "properties": {
                "command": {"type": "string", "description": "Commande shell à exécuter."},
                "cwd":     {"type": "string", "description": "Répertoire de travail (optionnel)."},
            },
            "required": ["command"],
        },
    ),
    handler=_run_bash,
)
