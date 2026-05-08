"""Outils filesystem pour Marius.

Standalone : dépend uniquement de kernel/tool_router et kernel/contracts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from marius.kernel.contracts import Artifact, ArtifactType, ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry


def _read_file(arguments: dict[str, Any]) -> ToolResult:
    path_str = arguments.get("path", "")
    if not path_str:
        return ToolResult(tool_call_id="", ok=False, summary="Argument `path` manquant.", error="missing_arg:path")

    path = Path(path_str).expanduser()
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
        lines = content.splitlines()
        summary = f"{path} ({len(lines)} lignes)"
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=content,
            data={"path": str(path), "lines": len(lines)},
            artifacts=[Artifact(type=ArtifactType.FILE, path=str(path), data={"content": content})],
        )
    except FileNotFoundError:
        return ToolResult(tool_call_id="", ok=False, summary=f"Fichier introuvable : {path}", error="file_not_found")
    except PermissionError:
        return ToolResult(tool_call_id="", ok=False, summary=f"Permission refusée : {path}", error="permission_denied")
    except Exception as exc:
        return ToolResult(tool_call_id="", ok=False, summary=str(exc), error=str(exc))


def _list_dir(arguments: dict[str, Any]) -> ToolResult:
    path_str = arguments.get("path", ".")
    path = Path(path_str).expanduser()

    try:
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
    except FileNotFoundError:
        return ToolResult(tool_call_id="", ok=False, summary=f"Dossier introuvable : {path}", error="dir_not_found")
    except PermissionError:
        return ToolResult(tool_call_id="", ok=False, summary=f"Permission refusée : {path}", error="permission_denied")

    lines = []
    for entry in entries:
        prefix = "📁 " if entry.is_dir() else "  "
        lines.append(f"{prefix}{entry.name}")

    summary = "\n".join(lines) if lines else "(dossier vide)"
    return ToolResult(
        tool_call_id="",
        ok=True,
        summary=summary,
        data={"path": str(path), "count": len(entries)},
    )


def _write_file(arguments: dict[str, Any]) -> ToolResult:
    path_str = arguments.get("path", "")
    content = arguments.get("content", "")

    if not path_str:
        return ToolResult(tool_call_id="", ok=False, summary="Argument `path` manquant.", error="missing_arg:path")

    path = Path(path_str).expanduser()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Fichier écrit : {path} ({len(content)} caractères)",
            data={"path": str(path), "chars": len(content)},
        )
    except PermissionError:
        return ToolResult(tool_call_id="", ok=False, summary=f"Permission refusée : {path}", error="permission_denied")
    except Exception as exc:
        return ToolResult(tool_call_id="", ok=False, summary=str(exc), error=str(exc))


# ── entrées du registre ───────────────────────────────────────────────────────

READ_FILE = ToolEntry(
    definition=ToolDefinition(
        name="read_file",
        description="Lit le contenu d'un fichier texte et le retourne.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin absolu ou relatif du fichier."},
            },
            "required": ["path"],
        },
    ),
    handler=_read_file,
)

LIST_DIR = ToolEntry(
    definition=ToolDefinition(
        name="list_dir",
        description="Liste les fichiers et dossiers dans un répertoire.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Chemin du répertoire (défaut : répertoire courant)."},
            },
            "required": [],
        },
    ),
    handler=_list_dir,
)

WRITE_FILE = ToolEntry(
    definition=ToolDefinition(
        name="write_file",
        description="Écrit du contenu dans un fichier (crée ou écrase).",
        parameters={
            "type": "object",
            "properties": {
                "path":    {"type": "string", "description": "Chemin du fichier à écrire."},
                "content": {"type": "string", "description": "Contenu à écrire."},
            },
            "required": ["path", "content"],
        },
    ),
    handler=_write_file,
)
