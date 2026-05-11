"""Observations courtes de session.

Brique standalone : extrait des faits vérifiés des résultats d'outils et les
formate pour le prompt système des tours suivants. Ces observations ne sont
pas persistées dans memory.db.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from marius.kernel.contracts import ToolCall, ToolResult

_METADATA_KEY = "session_observations"
_MAX_OBSERVATIONS = 24
_MAX_LISTED_PATHS = 10
_MAX_LINE_LEN = 220
_PREFIX_RE = re.compile(r"^[\s📁•*-]+")


def observe_tool_result(
    metadata: dict[str, Any],
    call: ToolCall,
    result: ToolResult,
    *,
    project_root: Path | None = None,
) -> None:
    """Met à jour `metadata` avec une observation courte si le résultat l'apporte."""
    observation = _observation_for(call, result, project_root=project_root)
    if not observation:
        return
    _append_observation(metadata, observation)


def format_session_observations(metadata: dict[str, Any]) -> str:
    observations = metadata.get(_METADATA_KEY)
    if not isinstance(observations, list) or not observations:
        return ""
    lines = ["<session_observations>"]
    lines.extend(f"- {str(item)}" for item in observations if str(item).strip())
    lines.append("</session_observations>")
    return "\n".join(lines)


def _observation_for(
    call: ToolCall,
    result: ToolResult,
    *,
    project_root: Path | None,
) -> str:
    target = _target_path(call, result)

    if call.name == "list_dir" and result.ok is True:
        listed = _listed_paths(result.summary)
        if not listed:
            return f"Dossier vérifié : `{_display_path(target, project_root)}`."
        shown = ", ".join(f"`{path}`" for path in listed[:_MAX_LISTED_PATHS])
        return f"Dossier vérifié `{_display_path(target, project_root)}` ; chemins listés : {shown}."

    if call.name in {"read_file", "write_file"} and result.ok is True:
        return f"Chemin fichier vérifié : `{_display_path(target, project_root)}`."

    if result.error == "file_not_found":
        candidates = _candidate_paths(result.summary)
        if candidates:
            shown = ", ".join(f"`{path}`" for path in candidates[:_MAX_LISTED_PATHS])
            return (
                f"Chemin invalide `{_display_path(target, project_root)}` ; "
                f"utiliser plutôt un candidat vérifié : {shown}."
            )
        return f"Chemin invalide `{_display_path(target, project_root)}` ; vérifier le dossier parent avant de réessayer."

    if result.error == "dir_not_found":
        return f"Dossier invalide `{_display_path(target, project_root)}` ; vérifier le dossier parent avant de réessayer."

    return ""


def _append_observation(metadata: dict[str, Any], observation: str) -> None:
    observation = " ".join(observation.split())
    if len(observation) > _MAX_LINE_LEN:
        observation = observation[: _MAX_LINE_LEN - 1].rstrip() + "…"
    current = metadata.get(_METADATA_KEY)
    observations = list(current) if isinstance(current, list) else []
    observations = [item for item in observations if item != observation]
    observations.append(observation)
    metadata[_METADATA_KEY] = observations[-_MAX_OBSERVATIONS:]


def _target_path(call: ToolCall, result: ToolResult) -> str:
    data_path = result.data.get("path") if isinstance(result.data, dict) else None
    if isinstance(data_path, str) and data_path.strip():
        return data_path
    for key in ("path", "file_path", "directory", "cwd"):
        value = call.arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return "."


def _display_path(path_str: str, project_root: Path | None) -> str:
    path = Path(path_str).expanduser()
    if project_root is None:
        return str(path)
    try:
        root = project_root.expanduser().resolve(strict=False)
        candidate = path if path.is_absolute() else root / path
        return str(candidate.resolve(strict=False).relative_to(root))
    except (OSError, RuntimeError, ValueError):
        return str(path)


def _listed_paths(summary: str) -> list[str]:
    paths: list[str] = []
    for raw_line in summary.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("Dossier :") or line.startswith("("):
            continue
        path = _PREFIX_RE.sub("", line).strip()
        if path:
            paths.append(path)
    return paths


def _candidate_paths(summary: str) -> list[str]:
    marker = "Candidat(s) existant(s) dans le projet :"
    if marker not in summary:
        return []
    tail = summary.split(marker, 1)[1]
    tail = tail.split(". Utilise", 1)[0]
    return [part.strip(" `") for part in tail.split(",") if part.strip(" `")]
