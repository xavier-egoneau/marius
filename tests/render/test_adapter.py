from __future__ import annotations

from datetime import datetime

from marius.kernel.contracts import Artifact, ArtifactType, CompactionNotice, Message, Role
from marius.render.adapter import (
    RenderSurface,
    render_artifact,
    render_compaction_notice,
    render_message,
)


def test_render_message_returns_plain_markdown_content_for_message_without_artifacts() -> None:
    message = Message(
        role=Role.ASSISTANT,
        content="Bonjour en **Markdown**.",
        created_at=datetime(2026, 5, 7, 15, 45, 0),
    )

    assert render_message(message) == "Bonjour en **Markdown**."


def test_render_message_appends_diff_artifact_as_fenced_diff_block() -> None:
    message = Message(
        role=Role.ASSISTANT,
        content="J’ai préparé le patch.",
        created_at=datetime(2026, 5, 7, 15, 46, 0),
        artifacts=[
            Artifact(
                type=ArtifactType.DIFF,
                path="marius/kernel/runtime.py",
                data={"patch": "@@ -1 +1 @@\n-old\n+new"},
            )
        ],
    )

    rendered = render_message(message)

    assert rendered.startswith("J’ai préparé le patch.")
    assert "**Diff — `marius/kernel/runtime.py`**" in rendered
    assert "```diff" in rendered
    assert "+new" in rendered


def test_render_compaction_notice_mentions_level_and_visible_history_guardrail() -> None:
    notice = CompactionNotice(
        level="summarize",
        summary="Anciennes étapes résumées.",
        metadata={"visible_history_untouched": True},
    )

    rendered = render_compaction_notice(notice)

    assert "summarize" in rendered
    assert "historique visible" in rendered
    assert "Anciennes étapes résumées." in rendered


def test_render_artifact_diff_falls_back_to_path_when_patch_content_is_missing() -> None:
    artifact = Artifact(type=ArtifactType.DIFF, path="changes.diff")

    rendered = render_artifact(artifact)

    assert "changes.diff" in rendered
    assert "```diff" not in rendered


def test_render_artifact_diff_uses_longer_markdown_fence_when_patch_contains_backticks() -> None:
    artifact = Artifact(
        type=ArtifactType.DIFF,
        path="README.md",
        data={"patch": "@@ -1 +1 @@\n-```\n+````"},
    )

    rendered = render_artifact(artifact)

    assert "`````diff" in rendered
    assert "@@ -1 +1 @@" in rendered
    assert "+````" in rendered


def test_render_surface_is_part_of_api_but_first_slice_keeps_portable_output_for_all_surfaces() -> None:
    message = Message(
        role=Role.ASSISTANT,
        content="Même rendu partout.",
        created_at=datetime(2026, 5, 7, 15, 47, 0),
        artifacts=[Artifact(type=ArtifactType.REPORT, path="report.txt")],
    )

    outputs = {
        surface: render_message(message, surface=surface)
        for surface in RenderSurface
    }

    assert len(set(outputs.values())) == 1
    assert outputs[RenderSurface.TELEGRAM].endswith("`report.txt`")


def test_render_message_keeps_non_diff_artifacts_visible_with_portable_fallback() -> None:
    message = Message(
        role=Role.ASSISTANT,
        content="Rapport prêt.",
        created_at=datetime(2026, 5, 7, 15, 48, 0),
        artifacts=[Artifact(type=ArtifactType.REPORT, path="report.txt")],
    )

    rendered = render_message(message)

    assert "Rapport prêt." in rendered
    assert "Artefact report disponible" in rendered
    assert "report.txt" in rendered
