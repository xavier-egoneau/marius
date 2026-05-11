"""Règles de posture conversationnelle.

Brique standalone : décide quand une session assistant bascule en posture dev.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from marius.kernel.contracts import ToolCall

ASSISTANT_SKILL = "assistant"
DEV_POSTURE = "dev"

_DEV_TRIGGER_TOOLS = {"read_file", "list_dir", "write_file", "run_bash"}
_PATH_KEYS = ("path", "file_path", "directory", "cwd")


def assistant_enabled(active_skills: list[str] | None) -> bool:
    return ASSISTANT_SKILL in set(active_skills or [])


def uses_dev_posture(active_skills: list[str] | None, metadata: dict[str, Any]) -> bool:
    return not assistant_enabled(active_skills) or metadata.get("posture") == DEV_POSTURE


def maybe_activate_dev_posture(
    metadata: dict[str, Any],
    active_skills: list[str] | None,
    call: ToolCall,
    project_root: Path,
) -> bool:
    """Active la posture dev pour une session assistant après un outil dev projet."""
    if not assistant_enabled(active_skills):
        return False
    if metadata.get("posture") == DEV_POSTURE:
        return False
    if not tool_call_triggers_dev(call, project_root):
        return False
    metadata["posture"] = DEV_POSTURE
    return True


def tool_call_triggers_dev(call: ToolCall, project_root: Path) -> bool:
    if call.name not in _DEV_TRIGGER_TOOLS:
        return False
    if call.name == "run_bash":
        cwd = call.arguments.get("cwd")
        if not cwd:
            return True
        return _is_under_project(str(cwd), project_root)

    path = _extract_path(call.arguments)
    if path is None:
        return True
    return _is_under_project(path, project_root)


def _extract_path(arguments: dict[str, Any]) -> str | None:
    for key in _PATH_KEYS:
        value = arguments.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return None


def _is_under_project(path: str, project_root: Path) -> bool:
    try:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = project_root / candidate
        resolved = candidate.resolve(strict=False)
        root = project_root.expanduser().resolve(strict=False)
        resolved.relative_to(root)
        return True
    except (OSError, RuntimeError, ValueError):
        return False
