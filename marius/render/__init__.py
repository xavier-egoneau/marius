"""Render layer: présentation visible selon surface.

Cette couche transforme les contrats kernel en rendu Markdown portable.
"""

from .adapter import (
    RenderSurface,
    render_artifact,
    render_artifacts,
    render_compaction_notice,
    render_message,
    render_turn_output,
)

__all__ = [
    "RenderSurface",
    "render_message",
    "render_turn_output",
    "render_compaction_notice",
    "render_artifact",
    "render_artifacts",
]
