"""Project exploration tools.

Standalone: stdlib only plus kernel contracts/tool_router.
These tools return observations to the model; they do not produce final chat
answers by themselves.
"""

from __future__ import annotations

import fnmatch
import json
import os
import re
import tomllib
from pathlib import Path
from typing import Any

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry

_SKIP_DIRS = {
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
_MAX_TREE_DEPTH = 6
_DEFAULT_TREE_DEPTH = 3
_MAX_TREE_ENTRIES = 240
_MAX_GREP_RESULTS = 80
_MAX_FILE_BYTES = 1_000_000


def _explore_tree(arguments: dict[str, Any]) -> ToolResult:
    root = Path(arguments.get("path") or ".").expanduser()
    depth = _bounded_int(arguments.get("depth"), default=_DEFAULT_TREE_DEPTH, minimum=0, maximum=_MAX_TREE_DEPTH)
    include_hidden = bool(arguments.get("include_hidden", False))

    if not root.exists():
        return ToolResult(tool_call_id="", ok=False, summary=f"Path not found: {root}", error="path_not_found")
    if not root.is_dir():
        return ToolResult(tool_call_id="", ok=False, summary=f"Not a directory: {root}", error="not_a_directory")

    lines = [f"{_display_path(root)}/"]
    entries: list[dict[str, Any]] = []
    truncated = False

    for current, dirs, files in os.walk(root):
        current_path = Path(current)
        rel_depth = _relative_depth(root, current_path)
        if rel_depth >= depth:
            dirs[:] = []
        dirs[:] = _visible_names(dirs, include_hidden)
        visible_files = _visible_names(files, include_hidden)

        children = [(name, True) for name in dirs] + [(name, False) for name in visible_files]
        children.sort(key=lambda item: (not item[1], item[0].lower()))
        for name, is_dir in children:
            child = current_path / name
            child_depth = _relative_depth(root, child)
            if child_depth > depth:
                continue
            if len(entries) >= _MAX_TREE_ENTRIES:
                truncated = True
                dirs[:] = []
                break
            prefix = "  " * child_depth
            suffix = "/" if is_dir else ""
            display = _display_path(child)
            lines.append(f"{prefix}{name}{suffix}")
            entries.append({"path": display, "type": "directory" if is_dir else "file"})
        if truncated:
            break

    if truncated:
        lines.append(f"... truncated after {_MAX_TREE_ENTRIES} entries")
    return ToolResult(
        tool_call_id="",
        ok=True,
        summary="\n".join(lines),
        data={"path": str(root), "depth": depth, "entries": entries, "truncated": truncated},
    )


def _explore_grep(arguments: dict[str, Any]) -> ToolResult:
    pattern = (arguments.get("pattern") or "").strip()
    if not pattern:
        return ToolResult(tool_call_id="", ok=False, summary="Argument `pattern` missing.", error="missing_arg:pattern")

    root = Path(arguments.get("path") or ".").expanduser()
    file_pattern = (arguments.get("file_pattern") or "*").strip() or "*"
    max_results = _bounded_int(arguments.get("max_results"), default=40, minimum=1, maximum=_MAX_GREP_RESULTS)
    regex = bool(arguments.get("regex", False))

    if not root.exists():
        return ToolResult(tool_call_id="", ok=False, summary=f"Path not found: {root}", error="path_not_found")

    try:
        compiled = re.compile(pattern, re.IGNORECASE) if regex else None
    except re.error as exc:
        return ToolResult(tool_call_id="", ok=False, summary=f"Invalid regex: {exc}", error="invalid_regex")

    files = [root] if root.is_file() else list(_iter_files(root, include_hidden=False))
    matches: list[dict[str, Any]] = []
    for path in files:
        if not fnmatch.fnmatch(path.name, file_pattern):
            continue
        text = _read_text_file(path)
        if text is None:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if compiled is not None:
                found = compiled.search(line) is not None
            else:
                found = pattern.lower() in line.lower()
            if not found:
                continue
            matches.append(
                {
                    "path": _display_path(path),
                    "line": line_no,
                    "text": line.strip(),
                }
            )
            if len(matches) >= max_results:
                break
        if len(matches) >= max_results:
            break

    if not matches:
        return ToolResult(tool_call_id="", ok=True, summary=f"No matches for {pattern!r}.", data={"matches": []})

    lines = [f"Matches for {pattern!r}:"]
    for match in matches:
        lines.append(f"- {match['path']}:{match['line']}: {match['text']}")
    return ToolResult(
        tool_call_id="",
        ok=True,
        summary="\n".join(lines),
        data={"matches": matches, "truncated": len(matches) >= max_results},
    )


def _explore_summary(arguments: dict[str, Any]) -> ToolResult:
    root = Path(arguments.get("path") or ".").expanduser()
    if not root.exists():
        return ToolResult(tool_call_id="", ok=False, summary=f"Path not found: {root}", error="path_not_found")
    if not root.is_dir():
        return ToolResult(tool_call_id="", ok=False, summary=f"Not a directory: {root}", error="not_a_directory")

    key_files = _detect_key_files(root)
    top_level = _top_level_entries(root)
    metadata = _project_metadata(root, key_files)

    lines = [f"Project summary: {_display_path(root)}"]
    if metadata:
        for key, value in metadata.items():
            lines.append(f"- {key}: {value}")
    if key_files:
        lines.append("- key files: " + ", ".join(key_files))
    if top_level:
        lines.append("- top level: " + ", ".join(top_level))

    return ToolResult(
        tool_call_id="",
        ok=True,
        summary="\n".join(lines),
        data={
            "path": str(root),
            "key_files": key_files,
            "top_level": top_level,
            "metadata": metadata,
        },
    )


EXPLORE_TREE = ToolEntry(
    definition=ToolDefinition(
        name="explore_tree",
        description="Return a compact project tree with common noise directories filtered out.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Directory to inspect. Defaults to current directory."},
                "depth": {"type": "integer", "description": "Maximum depth, default 3, max 6."},
                "include_hidden": {"type": "boolean", "description": "Include hidden files and directories."},
            },
            "required": [],
        },
    ),
    handler=_explore_tree,
)

EXPLORE_GREP = ToolEntry(
    definition=ToolDefinition(
        name="explore_grep",
        description="Search text in project files and return matching paths and line numbers.",
        parameters={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Text or regex to search for."},
                "path": {"type": "string", "description": "Directory or file to search. Defaults to current directory."},
                "file_pattern": {"type": "string", "description": "Filename glob such as '*.py'. Defaults to all files."},
                "max_results": {"type": "integer", "description": "Maximum matching lines, default 40, max 80."},
                "regex": {"type": "boolean", "description": "Interpret pattern as a regular expression."},
            },
            "required": ["pattern"],
        },
    ),
    handler=_explore_grep,
)

EXPLORE_SUMMARY = ToolEntry(
    definition=ToolDefinition(
        name="explore_summary",
        description="Inspect key project files and return a structured lightweight project summary.",
        parameters={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Project root. Defaults to current directory."},
            },
            "required": [],
        },
    ),
    handler=_explore_summary,
)


def _iter_files(root: Path, *, include_hidden: bool) -> list[Path]:
    paths: list[Path] = []
    for current, dirs, files in os.walk(root):
        dirs[:] = _visible_names(dirs, include_hidden)
        for name in _visible_names(files, include_hidden):
            paths.append(Path(current) / name)
    return paths


def _visible_names(names: list[str], include_hidden: bool) -> list[str]:
    visible = []
    for name in names:
        if name in _SKIP_DIRS:
            continue
        if not include_hidden and name.startswith("."):
            continue
        visible.append(name)
    return visible


def _read_text_file(path: Path) -> str | None:
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    if b"\x00" in data[:4096]:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace")


def _detect_key_files(root: Path) -> list[str]:
    names = [
        "README.md",
        "AGENTS.md",
        "DECISIONS.md",
        "ROADMAP.md",
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "requirements.txt",
        "Makefile",
    ]
    return [name for name in names if (root / name).exists()]


def _project_metadata(root: Path, key_files: list[str]) -> dict[str, str]:
    metadata: dict[str, str] = {}
    if "pyproject.toml" in key_files:
        try:
            data = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
            project = data.get("project", {})
            if isinstance(project, dict):
                if project.get("name"):
                    metadata["name"] = str(project["name"])
                if project.get("requires-python"):
                    metadata["python"] = str(project["requires-python"])
        except (OSError, tomllib.TOMLDecodeError):
            pass
    if "package.json" in key_files:
        try:
            data = json.loads((root / "package.json").read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if data.get("name"):
                    metadata["name"] = str(data["name"])
                scripts = data.get("scripts")
                if isinstance(scripts, dict) and scripts:
                    metadata["npm_scripts"] = ", ".join(sorted(str(key) for key in scripts)[:8])
        except (OSError, json.JSONDecodeError):
            pass
    return metadata


def _top_level_entries(root: Path, limit: int = 24) -> list[str]:
    try:
        children = sorted(root.iterdir(), key=lambda path: (path.is_file(), path.name.lower()))
    except OSError:
        return []
    entries = []
    for child in children:
        if child.name in _SKIP_DIRS or child.name.startswith("."):
            continue
        suffix = "/" if child.is_dir() else ""
        entries.append(child.name + suffix)
        if len(entries) >= limit:
            break
    return entries


def _relative_depth(root: Path, path: Path) -> int:
    try:
        return len(path.relative_to(root).parts)
    except ValueError:
        return 0


def _display_path(path: Path) -> str:
    try:
        return str(path.resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)))
    except (OSError, RuntimeError, ValueError):
        return str(path)


def _bounded_int(value: object, *, default: int, minimum: int, maximum: int) -> int:
    if not isinstance(value, int):
        return default
    return max(minimum, min(value, maximum))
