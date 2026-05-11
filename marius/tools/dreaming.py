"""Dreaming and daily tools.

Dynamic ToolEntry wrappers around the existing dreaming engine. They need the
current provider, memory store and project root, so they are built by the tool
factory per agent/session.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from marius.dreaming.engine import run_daily, run_dreaming
from marius.kernel.contracts import Artifact, ArtifactType, ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.provider_config.contracts import ProviderEntry
from marius.storage.memory_store import MemoryStore


def make_dreaming_tools(
    *,
    memory_store: MemoryStore,
    entry: ProviderEntry,
    project_root: Path,
    active_skills: list[str] | None = None,
    sessions_dir: Path | None = None,
    dreams_dir: Path | None = None,
    skills_dir: Path | None = None,
    watch_dir: Path | None = None,
) -> dict[str, ToolEntry]:
    root = Path(project_root)

    def dreaming_run(arguments: dict[str, Any]) -> ToolResult:
        archive_sessions = _optional_bool(arguments.get("archive_sessions"), True)
        result = run_dreaming(
            memory_store=memory_store,
            entry=entry,
            active_skills=active_skills,
            project_root=root,
            sessions_dir=sessions_dir,
            dreams_dir=dreams_dir,
            skills_dir=skills_dir,
            watch_dir=watch_dir,
            archive_sessions=archive_sessions,
        )
        return ToolResult(
            tool_call_id="",
            ok=result.errors == 0,
            summary=str(result),
            data={
                "added": result.added,
                "updated": result.updated,
                "removed": result.removed,
                "errors": result.errors,
                "raw_ops": result.raw_ops,
                "archive_sessions": archive_sessions,
                "project_root": str(root),
            },
            error="dreaming_failed" if result.errors else None,
        )

    def daily_digest(arguments: dict[str, Any]) -> ToolResult:
        briefing = run_daily(
            memory_store=memory_store,
            entry=entry,
            active_skills=active_skills,
            project_root=root,
            dreams_dir=dreams_dir,
            skills_dir=skills_dir,
            watch_dir=watch_dir,
        )
        summary = _markdown_summary(briefing)
        return ToolResult(
            tool_call_id="",
            ok=not briefing.startswith("# Briefing\n\nErreur provider"),
            summary=summary,
            data={
                "markdown": briefing,
                "project_root": str(root),
            },
            artifacts=[
                Artifact(
                    type=ArtifactType.REPORT,
                    data={"format": "markdown", "content": briefing},
                )
            ],
            error="daily_failed" if briefing.startswith("# Briefing\n\nErreur provider") else None,
        )

    return {
        "dreaming_run": ToolEntry(
            definition=ToolDefinition(
                name="dreaming_run",
                description="Run memory consolidation using Marius dreaming and return a structured observation.",
                parameters={
                    "type": "object",
                    "properties": {
                        "archive_sessions": {
                            "type": "boolean",
                            "description": "Archive processed session corpus files after consolidation. Default true.",
                        },
                    },
                    "required": [],
                },
            ),
            handler=dreaming_run,
        ),
        "daily_digest": ToolEntry(
            definition=ToolDefinition(
                name="daily_digest",
                description="Generate the daily briefing markdown from memories, skill daily contracts and watch reports.",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            handler=daily_digest,
        ),
    }


def _optional_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "y", "oui", "o", "on")
    return bool(value)


def _markdown_summary(markdown: str, *, limit: int = 400) -> str:
    text = "\n".join(line.strip() for line in markdown.splitlines() if line.strip())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"
