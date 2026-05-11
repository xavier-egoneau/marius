from __future__ import annotations

from marius.kernel.contracts import Artifact, ArtifactType, ToolResult
from marius.kernel.tool_result_context import format_tool_result_for_context


def test_format_tool_result_for_context_includes_structured_data() -> None:
    result = ToolResult(
        tool_call_id="call-1",
        ok=True,
        summary="1 result",
        data={
            "results": [
                {
                    "title": "Marius",
                    "url": "https://example.test/marius",
                    "content": "Search snippet.",
                }
            ]
        },
    )

    formatted = format_tool_result_for_context(result)

    assert "summary: 1 result" in formatted
    assert "data:" in formatted
    assert "https://example.test/marius" in formatted
    assert "Search snippet." in formatted


def test_format_tool_result_for_context_redacts_sensitive_keys() -> None:
    result = ToolResult(
        tool_call_id="call-1",
        ok=True,
        summary="provider configured",
        data={
            "api_key": "sk-secret",
            "nested": {"telegram_token": "123:secret"},
            "public": "visible",
        },
    )

    formatted = format_tool_result_for_context(result)

    assert "[redacted]" in formatted
    assert "visible" in formatted
    assert "sk-secret" not in formatted
    assert "123:secret" not in formatted


def test_format_tool_result_for_context_includes_artifacts_and_is_bounded() -> None:
    result = ToolResult(
        tool_call_id="call-1",
        ok=True,
        summary="report",
        artifacts=[
            Artifact(
                type=ArtifactType.REPORT,
                path="report.md",
                data={"content": "x" * 500},
            )
        ],
    )

    formatted = format_tool_result_for_context(result, limit=180)

    assert len(formatted) <= 180
    assert "artifacts:" in formatted
    assert "[tool observation truncated]" in formatted
