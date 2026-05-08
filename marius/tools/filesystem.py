"""Outils filesystem pour Marius.

Standalone : dépend uniquement de kernel/tool_router et kernel/contracts.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from marius.kernel.contracts import Artifact, ArtifactType, ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_MAX_MISSING_PATH_CANDIDATES = 5
_MAX_MISSING_PATH_DEPTH = 6
_MAX_MISSING_PATH_VISITS = 3000
_SKIP_SEARCH_DIRS = {
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "vendor",
}


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
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=_missing_file_summary(path),
            error="file_not_found",
        )
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
        return ToolResult(
            tool_call_id="",
            ok=False,
            summary=f"Dossier introuvable : {path}. Liste le dossier parent avant de réessayer.",
            error="dir_not_found",
        )
    except PermissionError:
        return ToolResult(tool_call_id="", ok=False, summary=f"Permission refusée : {path}", error="permission_denied")

    display_path = _display_path(path)
    visible_entries = [entry for entry in entries if not _skip_display_entry(entry)]
    lines = [f"Dossier : {display_path}"]
    for entry in visible_entries:
        prefix = "📁 " if entry.is_dir() else "  "
        lines.append(f"{prefix}{_display_path(entry)}")

    if not visible_entries:
        lines.append("(dossier vide)")
    summary = "\n".join(lines)
    return ToolResult(
        tool_call_id="",
        ok=True,
        summary=summary,
        data={"path": str(path), "count": len(visible_entries)},
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


def _missing_file_summary(path: Path) -> str:
    candidates = _find_missing_file_candidates(path)
    if not candidates:
        return f"Fichier introuvable : {path}. Liste le dossier parent avant de réessayer."

    formatted = ", ".join(candidates)
    return (
        f"Fichier introuvable : {path}. "
        f"Candidat(s) existant(s) dans le projet : {formatted}. "
        "Utilise un chemin listé ou liste le dossier parent avant de réessayer."
    )


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)))
    except (OSError, RuntimeError, ValueError):
        return str(path)


def _skip_display_entry(path: Path) -> bool:
    name = path.name
    return name in _SKIP_SEARCH_DIRS or name.startswith(".")


def _find_missing_file_candidates(path: Path) -> list[str]:
    if not path.name:
        return []

    root = Path.cwd()
    requested_suffix = _path_suffix(path)
    exact_suffix_matches: list[str] = []
    same_name_matches: list[str] = []
    visited = 0

    for current_root, dirs, files in os.walk(root):
        current = Path(current_root)
        dirs[:] = [d for d in dirs if d not in _SKIP_SEARCH_DIRS and not d.startswith(".")]
        depth = len(current.relative_to(root).parts)
        if depth >= _MAX_MISSING_PATH_DEPTH:
            dirs[:] = []

        visited += len(dirs) + len(files)
        if visited > _MAX_MISSING_PATH_VISITS:
            break

        if path.name not in files:
            continue

        candidate = current / path.name
        try:
            display = str(candidate.relative_to(root))
        except ValueError:
            display = str(candidate)

        if requested_suffix and tuple(Path(display).parts[-len(requested_suffix):]) == requested_suffix:
            exact_suffix_matches.append(display)
        else:
            same_name_matches.append(display)

        if len(exact_suffix_matches) + len(same_name_matches) >= _MAX_MISSING_PATH_CANDIDATES:
            break

    return (exact_suffix_matches + same_name_matches)[:_MAX_MISSING_PATH_CANDIDATES]


def _path_suffix(path: Path) -> tuple[str, ...]:
    parts = tuple(part for part in path.parts if part not in ("", "."))
    if path.is_absolute() or len(parts) <= 1:
        return ()
    return parts
