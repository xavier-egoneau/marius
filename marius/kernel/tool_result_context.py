"""Formatting of tool observations injected back into provider context."""

from __future__ import annotations

import json
from typing import Any

from marius.kernel.contracts import ToolResult

_DEFAULT_LIMIT = 12_000
_SENSITIVE_KEY_PARTS = ("secret", "token", "api_key", "apikey", "password")


def format_tool_result_for_context(result: ToolResult, *, limit: int = _DEFAULT_LIMIT) -> str:
    """Return a bounded, structured observation for the LLM.

    Tool summaries are useful for UI traces, but the model needs the structured
    payload too. This helper keeps the LLM in the loop without letting tools
    become final answers.
    """
    sections = [
        f"ok: {result.ok}",
        f"summary: {result.summary}",
    ]
    if result.error:
        sections.append(f"error: {result.error}")
    if result.data:
        data = _json_dumps(_redact(result.data))
        sections.append(f"data:\n```json\n{data}\n```")
    if result.artifacts:
        artifacts = [
            {"type": artifact.type.value, "path": artifact.path, "data": _redact(artifact.data)}
            for artifact in result.artifacts
        ]
        sections.append(f"artifacts:\n```json\n{_json_dumps(artifacts)}\n```")
    return _truncate("\n\n".join(sections), limit=limit)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, default=str)


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if any(part in key_text.lower() for part in _SENSITIVE_KEY_PARTS):
                redacted[key_text] = "[redacted]"
            else:
                redacted[key_text] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _truncate(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 32:
        return text[:limit]
    return text[: max(0, limit - 32)].rstrip() + "\n\n[tool observation truncated]"
