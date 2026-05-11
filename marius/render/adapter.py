from __future__ import annotations

from enum import Enum
import re

from marius.kernel.contracts import Artifact, ArtifactType, CompactionNotice, Message, ToolResult


class RenderSurface(str, Enum):
    PORTABLE = "portable"
    CLI = "cli"
    TELEGRAM = "telegram"
    WEB = "web"


def render_message(
    message: Message,
    *,
    surface: RenderSurface = RenderSurface.PORTABLE,
) -> str:
    if not message.visible:
        return ""
    sections: list[str] = [message.content]
    artifacts = render_artifacts(message.artifacts, surface=surface)
    if artifacts:
        sections.append(artifacts)
    return "\n\n".join(section for section in sections if section)


def render_turn_output(
    assistant_message: Message | None,
    *,
    tool_results: list[ToolResult] | None = None,
    compaction_notice: CompactionNotice | None = None,
    surface: RenderSurface = RenderSurface.PORTABLE,
) -> str:
    """Render the visible end-of-turn payload without making tools speak.

    Tool artifacts are observations attached to the turn. The LLM still owns the
    narrative answer; this helper only appends portable artifact fallbacks and
    kernel notices that would otherwise be lost by channel-specific code.
    """
    sections: list[str] = []
    artifacts: list[Artifact] = []
    if assistant_message is not None and assistant_message.visible:
        if assistant_message.content:
            sections.append(assistant_message.content)
        artifacts.extend(assistant_message.artifacts)
    for result in tool_results or []:
        artifacts.extend(result.artifacts)
    rendered_artifacts = render_artifacts(artifacts, surface=surface)
    if rendered_artifacts:
        sections.append(rendered_artifacts)
    if compaction_notice is not None:
        sections.append(render_compaction_notice(compaction_notice, surface=surface))
    return "\n\n".join(section for section in sections if section)


def render_artifacts(
    artifacts: list[Artifact],
    *,
    surface: RenderSurface = RenderSurface.PORTABLE,
) -> str:
    rendered: list[str] = []
    seen: set[tuple[str, str, tuple[tuple[str, str], ...]]] = set()
    for artifact in artifacts:
        fingerprint = _artifact_fingerprint(artifact)
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        section = render_artifact(artifact, surface=surface)
        if section:
            rendered.append(section)
    return "\n\n".join(rendered)


def render_compaction_notice(
    notice: CompactionNotice,
    *,
    surface: RenderSurface = RenderSurface.PORTABLE,
) -> str:
    del surface
    lines = [f"> **Contexte compacté (`{notice.level}`)**"]
    if notice.metadata.get("visible_history_untouched"):
        lines.append("> L’historique visible utilisateur reste intact.")
    if notice.summary:
        lines.append(f"> Résumé : {notice.summary}")
    return "\n".join(lines)


def render_artifact(
    artifact: Artifact,
    *,
    surface: RenderSurface = RenderSurface.PORTABLE,
) -> str:
    del surface
    if artifact.data.get("display") is False:
        return ""
    if artifact.type is ArtifactType.DIFF:
        patch = _resolve_diff_content(artifact)
        label = artifact.path or str(artifact.data.get("path", "diff"))
        if patch:
            fence = _markdown_fence_for(patch)
            return f"**Diff — `{label}`**\n{fence}diff\n{patch}\n{fence}"
        return f"**Diff disponible** : `{label}`"

    label = artifact.path or str(artifact.data.get("path", artifact.type.value))
    if artifact.type is ArtifactType.REPORT:
        content = _resolve_text_content(artifact)
        if content:
            return f"**Rapport — `{label}`**\n\n{content.strip()}"
    return f"**Artefact {artifact.type.value} disponible** : `{label}`"


def _resolve_diff_content(artifact: Artifact) -> str:
    for key in ("patch", "diff", "content"):
        value = artifact.data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _resolve_text_content(artifact: Artifact) -> str:
    value = artifact.data.get("content")
    return value if isinstance(value, str) and value.strip() else ""


def _markdown_fence_for(content: str) -> str:
    runs = re.findall(r"`+", content)
    longest_run = max((len(run) for run in runs), default=0)
    return "`" * max(3, longest_run + 1)


def _artifact_fingerprint(artifact: Artifact) -> tuple[str, str, tuple[tuple[str, str], ...]]:
    return (
        artifact.type.value,
        artifact.path,
        tuple(sorted((str(key), repr(value)) for key, value in artifact.data.items())),
    )
