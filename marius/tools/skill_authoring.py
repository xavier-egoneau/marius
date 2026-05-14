"""Markdown-first skill authoring tools.

Standalone: depends only on stdlib plus kernel skill/tool contracts.
The tools create and inspect portable skill folders; they do not activate
skills or replace the model's final answer.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from marius.kernel.contracts import ToolResult
from marius.kernel.skills import SkillReader, collect_skill_commands
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_MARIUS_HOME = Path.home() / ".marius"
_DEFAULT_SKILLS_DIR = _MARIUS_HOME / "skills"
_SKILL_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")
_COMMAND_NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")


def make_skill_authoring_tools(skills_dir: Path | None = None) -> dict[str, ToolEntry]:
    root = Path(skills_dir) if skills_dir is not None else _DEFAULT_SKILLS_DIR

    def skill_create(arguments: dict[str, Any]) -> ToolResult:
        name = (arguments.get("name") or "").strip()
        description = (arguments.get("description") or "").strip()
        body = (arguments.get("body") or "").strip()
        commands = _command_names(arguments.get("commands"))
        include_dream = bool(arguments.get("include_dream", False))
        overwrite = bool(arguments.get("overwrite", False))

        if not _valid_skill_name(name):
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Invalid skill name. Use lowercase letters, digits, '-' or '_', starting with a letter.",
                error="invalid_skill_name",
            )
        if not description:
            return ToolResult(tool_call_id="", ok=False, summary="Argument `description` missing.", error="missing_arg:description")
        if any(not _valid_command_name(command) for command in commands):
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Invalid command name. Commands use lowercase letters, digits, '-' or '_'.",
                error="invalid_command_name",
            )

        skill_dir = root / name
        if skill_dir.exists() and not overwrite:
            return ToolResult(tool_call_id="", ok=False, summary=f"Skill already exists: {name}", error="skill_exists")

        skill_dir.mkdir(parents=True, exist_ok=True)
        (skill_dir / "SKILL.md").write_text(
            _skill_markdown(name=name, description=description, body=body, commands=commands),
            encoding="utf-8",
        )
        if include_dream:
            (skill_dir / "DREAM.md").write_text(
                "# Dream contract\n\nDescribe what this skill can surface during memory consolidation.\n",
                encoding="utf-8",
            )
        if commands:
            core_dir = skill_dir / "core"
            core_dir.mkdir(exist_ok=True)
            for command in commands:
                (core_dir / f"{command}.md").write_text(
                    _command_markdown(command),
                    encoding="utf-8",
                )

        created = ["SKILL.md"]
        if include_dream:
            created.append("DREAM.md")
        created.extend(f"core/{command}.md" for command in commands)
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Skill created: {name} ({', '.join(created)})",
            data={"name": name, "path": str(skill_dir), "files": created, "commands": commands},
        )

    def skill_list(arguments: dict[str, Any]) -> ToolResult:
        include_commands = bool(arguments.get("include_commands", True))
        reader = SkillReader(root)
        metas = reader.list()
        rows = []
        lines = ["Available skills:"]
        for meta in metas:
            skill = reader.load(meta.name) if include_commands else None
            commands = sorted((skill.commands or {}).keys()) if skill is not None else []
            suffix = f" commands: {', '.join(commands)}" if commands else ""
            desc = f" - {meta.description}" if meta.description else ""
            lines.append(f"- {meta.name}{desc}{suffix}")
            rows.append(
                {
                    "name": meta.name,
                    "description": meta.description,
                    "version": meta.version,
                    "path": str(meta.skill_dir),
                    "commands": commands,
                }
            )
        if not rows:
            lines.append("(none)")
        return ToolResult(tool_call_id="", ok=True, summary="\n".join(lines), data={"skills": rows})

    def skill_reload(arguments: dict[str, Any]) -> ToolResult:
        reader = SkillReader(root)
        skills = reader.load_all([meta.name for meta in reader.list()])
        commands = collect_skill_commands(skills)
        command_rows = [
            {"name": name, "description": command.description, "skill": command.skill_name}
            for name, command in sorted(commands.items())
        ]
        summary = (
            f"Skills reloaded from disk: {len(skills)} skill(s), "
            f"{len(command_rows)} command(s). Changes apply when the active context is rebuilt."
        )
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=summary,
            data={
                "skills": [skill.meta.name for skill in skills],
                "commands": command_rows,
                "skills_dir": str(root),
            },
        )

    return {
        "skill_create": ToolEntry(
            definition=ToolDefinition(
                name="skill_create",
                description="Create a portable Markdown-first skill folder under the configured skills directory.",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Skill name, lowercase slug."},
                        "description": {"type": "string", "description": "Short description for discovery."},
                        "body": {"type": "string", "description": "Main SKILL.md instruction body."},
                        "commands": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional slash command names to scaffold under core/.",
                        },
                        "include_dream": {"type": "boolean", "description": "Create DREAM.md placeholder."},
                        "overwrite": {"type": "boolean", "description": "Replace an existing skill folder."},
                    },
                    "required": ["name", "description"],
                },
            ),
            handler=skill_create,
        ),
        "skill_list": ToolEntry(
            definition=ToolDefinition(
                name="skill_list",
                description="List installed skills and their Markdown-declared commands.",
                parameters={
                    "type": "object",
                    "properties": {
                        "include_commands": {"type": "boolean", "description": "Include commands discovered in core/."},
                    },
                    "required": [],
                },
            ),
            handler=skill_list,
        ),
        "skill_reload": ToolEntry(
            definition=ToolDefinition(
                name="skill_reload",
                description="Reload skills from disk and return a validation snapshot for future context rebuilds.",
                parameters={"type": "object", "properties": {}, "required": []},
            ),
            handler=skill_reload,
        ),
    }


_DEFAULT_TOOLS = make_skill_authoring_tools()
SKILL_CREATE = _DEFAULT_TOOLS["skill_create"]
SKILL_LIST = _DEFAULT_TOOLS["skill_list"]
SKILL_RELOAD = _DEFAULT_TOOLS["skill_reload"]


def _valid_skill_name(name: str) -> bool:
    return bool(_SKILL_NAME_RE.fullmatch(name))


def _valid_command_name(name: str) -> bool:
    return bool(_COMMAND_NAME_RE.fullmatch(name))


def _command_names(raw: object) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(item).strip() for item in raw if str(item).strip()]
    return []


def _skill_markdown(*, name: str, description: str, body: str, commands: list[str]) -> str:
    frontmatter = [
        "---",
        f"name: {name}",
        f"description: {description}",
    ]
    if commands:
        frontmatter.append(f"commands: {', '.join(commands)}")
    frontmatter.append("---")
    content = body or (
        "This skill describes a reusable working posture.\n\n"
        "Keep instructions portable, Markdown-first, and independent from local absolute paths."
    )
    return "\n".join(frontmatter) + "\n\n" + content.strip() + "\n"


def _command_markdown(command: str) -> str:
    return (
        "---\n"
        f"description: {command}\n"
        "---\n"
        f"You are handling /{command}. Replace this placeholder with the command protocol.\n"
    )
