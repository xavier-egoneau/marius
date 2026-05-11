from __future__ import annotations

from datetime import datetime

from rich.console import Console
from rich.markdown import Markdown

from marius.kernel.contracts import Artifact, ArtifactType, Message, Role, ToolResult
from marius.render.adapter import RenderSurface, render_turn_output


def test_cli_rich_markdown_renders_turn_output_artifacts() -> None:
    markdown = render_turn_output(
        Message(
            role=Role.ASSISTANT,
            content="Patch prêt.",
            created_at=datetime(2026, 5, 11, 10, 0, 0),
        ),
        tool_results=[
            ToolResult(
                tool_call_id="tool-1",
                ok=True,
                artifacts=[
                    Artifact(
                        type=ArtifactType.DIFF,
                        path="README.md",
                        data={"patch": "@@ -1 +1 @@\n-old\n+new"},
                    )
                ],
            )
        ],
        surface=RenderSurface.CLI,
    )
    console = Console(record=True, width=100, force_terminal=False)

    console.print(Markdown(markdown))
    rendered = console.export_text()

    assert "Patch prêt." in rendered
    assert "Diff" in rendered
    assert "README.md" in rendered
    assert "+new" in rendered
