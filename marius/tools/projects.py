"""Project registry tools.

Standalone wrapper around ProjectStore. The tools expose explicit project
context to the LLM without changing the final-answer contract.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.storage.project_store import ActiveProject, ProjectEntry, ProjectStore


def make_project_tools(
    *,
    cwd: Path | None = None,
    store_path: Path | None = None,
    active_path: Path | None = None,
    allow_store_path: Path | None = None,
) -> dict[str, ToolEntry]:
    store = ProjectStore(store_path=store_path, active_path=active_path)
    base_cwd = Path(cwd).expanduser().resolve() if cwd is not None else Path.cwd()

    def project_list(arguments: dict[str, Any]) -> ToolResult:
        limit = _bounded_int(arguments.get("limit"), default=20, minimum=1, maximum=100)
        active = store.get_active()
        projects = store.load()[:limit]
        lines = []
        if active is None:
            lines.append("No active project is set.")
        else:
            lines.append(f"Active project: {active.name} ({active.path}).")
        lines.append(f"Known projects: {len(projects)} shown.")
        for project in projects:
            marker = " *" if active and project.path == active.path else ""
            lines.append(f"- {project.name}{marker}: {project.path}")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary="\n".join(lines),
            data={
                "active_project": _active_data(active) if active else None,
                "projects": [_project_data(project) for project in projects],
                "limit": limit,
            },
        )

    def project_set_active(arguments: dict[str, Any]) -> ToolResult:
        raw_path = _optional_text(arguments.get("path"))
        name = _optional_text(arguments.get("name"))
        create = bool(arguments.get("create", False))
        project_path = _resolve_project_path(store, path=raw_path, name=name, cwd=base_cwd)
        if project_path is None:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Project not found. Provide `path` or a known project `name`.",
                error="project_not_found",
            )
        if not project_path.exists():
            if create:
                try:
                    project_path.mkdir(parents=True, exist_ok=True)
                except OSError as exc:
                    return ToolResult(
                        tool_call_id="",
                        ok=False,
                        summary=f"Project path could not be created: {project_path}",
                        error=str(exc),
                    )
            else:
                return ToolResult(
                    tool_call_id="",
                    ok=False,
                    summary=f"Project path does not exist: {project_path}",
                    error="project_path_missing",
                )
        if not project_path.is_dir():
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary=f"Project path is not a directory: {project_path}",
                error="project_path_not_directory",
            )
        active = store.set_active(project_path)
        if allow_store_path is not None:
            from marius.storage.allow_root_store import AllowRootStore

            AllowRootStore(allow_store_path).add(project_path, reason="project_set_active")
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Active project set: {active.name} ({active.path}).",
            data={"active_project": _active_data(active)},
        )

    return {
        "project_list": ToolEntry(
            definition=ToolDefinition(
                name="project_list",
                description="List known Marius projects and the explicit active project.",
                parameters={
                    "type": "object",
                    "properties": {
                        "limit": {"type": "integer", "description": "Maximum number of projects to return."},
                    },
                    "required": [],
                },
            ),
            handler=project_list,
        ),
        "project_set_active": ToolEntry(
            definition=ToolDefinition(
                name="project_set_active",
                description=(
                    "Set the explicit active project by path or known project name. "
                    "Use it when the user clearly asks to work on a known project; "
                    "if another project is only mentioned as a reference or comparison, ask before switching. "
                    "For a natural request to create a brand-new project, prefer creating a Kanban task "
                    "with project_path='nouveau'. Inside that task, use this tool only if work must continue "
                    "inside the new project after the directory is created; if the task only creates the project, "
                    "do not change the active project."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Project root path."},
                        "name": {"type": "string", "description": "Known project name."},
                        "create": {"type": "boolean", "description": "If true, create the project directory before setting it active."},
                    },
                    "required": [],
                },
            ),
            handler=project_set_active,
        ),
    }


_DEFAULT_TOOLS = make_project_tools()
PROJECT_LIST = _DEFAULT_TOOLS["project_list"]
PROJECT_SET_ACTIVE = _DEFAULT_TOOLS["project_set_active"]


def _resolve_project_path(store: ProjectStore, *, path: str | None, name: str | None, cwd: Path) -> Path | None:
    if path:
        candidate = Path(path).expanduser()
        if not candidate.is_absolute():
            candidate = cwd / candidate
        return candidate
    if not name:
        return None
    candidates = [project for project in store.load() if project.name == name or project.path == name]
    if len(candidates) == 1:
        return Path(candidates[0].path)
    return None


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


def _project_data(project: ProjectEntry) -> dict[str, Any]:
    return {
        "path": project.path,
        "name": project.name,
        "last_opened": project.last_opened,
        "session_count": project.session_count,
    }


def _active_data(active: ActiveProject) -> dict[str, Any]:
    return {
        "path": active.path,
        "name": active.name,
        "set_at": active.set_at,
    }
