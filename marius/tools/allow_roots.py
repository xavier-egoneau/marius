"""Tools for managing explicit filesystem allow roots."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from marius.kernel.contracts import ToolResult
from marius.kernel.tool_router import ToolDefinition, ToolEntry
from marius.storage.allow_root_store import AllowRootStore


def make_allow_root_tools(*, store_path: Path | None = None) -> dict[str, ToolEntry]:
    store = AllowRootStore(store_path)

    def allow_root_list(arguments: dict[str, Any]) -> ToolResult:
        roots = store.list()
        if not roots:
            summary = "No explicit allowed filesystem roots."
        else:
            lines = [f"Allowed roots: {len(roots)}."]
            for root in roots:
                reason = f" ({root.reason})" if root.reason else ""
                lines.append(f"- {root.path}{reason}")
            summary = "\n".join(lines)
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=summary,
            data={"allowed_roots": [_root_data(root) for root in roots]},
        )

    def allow_root_add(arguments: dict[str, Any]) -> ToolResult:
        raw_path = _optional_text(arguments.get("path"))
        if raw_path is None:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Provide `path` to add an allowed filesystem root.",
                error="missing_path",
            )
        reason = _optional_text(arguments.get("reason")) or "allow_root_add"
        root = store.add(Path(raw_path), reason=reason)
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Allowed root added: {root.path}.",
            data={"allowed_root": _root_data(root)},
        )

    def allow_root_remove(arguments: dict[str, Any]) -> ToolResult:
        raw_path = _optional_text(arguments.get("path"))
        if raw_path is None:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary="Provide `path` to remove an allowed filesystem root.",
                error="missing_path",
            )
        removed = store.remove(Path(raw_path))
        resolved = Path(raw_path).expanduser().resolve(strict=False)
        if not removed:
            return ToolResult(
                tool_call_id="",
                ok=False,
                summary=f"Allowed root not found: {resolved}.",
                error="allow_root_not_found",
                data={"path": str(resolved)},
            )
        return ToolResult(
            tool_call_id="",
            ok=True,
            summary=f"Allowed root removed: {resolved}.",
            data={"path": str(resolved)},
        )

    return {
        "allow_root_list": ToolEntry(
            definition=ToolDefinition(
                name="allow_root_list",
                description=(
                    "List explicit filesystem roots that Marius may treat as trusted workspaces."
                ),
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            ),
            handler=allow_root_list,
        ),
        "allow_root_add": ToolEntry(
            definition=ToolDefinition(
                name="allow_root_add",
                description=(
                    "Add an explicit trusted filesystem root. Use when the user asks to authorize "
                    "a folder or make a project/workspace accessible."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Folder path to authorize."},
                        "reason": {"type": "string", "description": "Short reason for the authorization."},
                    },
                    "required": ["path"],
                },
            ),
            handler=allow_root_add,
        ),
        "allow_root_remove": ToolEntry(
            definition=ToolDefinition(
                name="allow_root_remove",
                description="Remove an explicit trusted filesystem root from Marius.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Folder path to remove from the allow list."},
                    },
                    "required": ["path"],
                },
            ),
            handler=allow_root_remove,
        ),
    }


_DEFAULT_TOOLS = make_allow_root_tools()
ALLOW_ROOT_LIST = _DEFAULT_TOOLS["allow_root_list"]
ALLOW_ROOT_ADD = _DEFAULT_TOOLS["allow_root_add"]
ALLOW_ROOT_REMOVE = _DEFAULT_TOOLS["allow_root_remove"]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _root_data(root: object) -> dict[str, str]:
    return {
        "path": str(getattr(root, "path", "")),
        "reason": str(getattr(root, "reason", "")),
        "added_at": str(getattr(root, "added_at", "")),
    }
