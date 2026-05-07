from __future__ import annotations

from enum import Enum
import re

from marius.kernel.contracts import Artifact, ArtifactType, CompactionNotice, Message


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
    sections: list[str] = [message.content]
    rendered_artifacts = [
        render_artifact(artifact, surface=surface)
        for artifact in message.artifacts
    ]
    if rendered_artifacts:
        sections.extend(section for section in rendered_artifacts if section)
    return "\n\n".join(section for section in sections if section)


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
    if artifact.type is ArtifactType.DIFF:
        patch = _resolve_diff_content(artifact)
        label = artifact.path or str(artifact.data.get("path", "diff"))
        if patch:
            fence = _markdown_fence_for(patch)
            return f"**Diff — `{label}`**\n{fence}diff\n{patch}\n{fence}"
        return f"**Diff disponible** : `{label}`"

    label = artifact.path or str(artifact.data.get("path", artifact.type.value))
    return f"**Artefact {artifact.type.value} disponible** : `{label}`"


def _resolve_diff_content(artifact: Artifact) -> str:
    for key in ("patch", "diff", "content"):
        value = artifact.data.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _markdown_fence_for(content: str) -> str:
    runs = re.findall(r"`+", content)
    longest_run = max((len(run) for run in runs), default=0)
    return "`" * max(3, longest_run + 1)
