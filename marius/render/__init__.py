"""Render layer: présentation visible selon surface.

Cette couche transforme les contrats kernel en rendu Markdown portable.
"""

from .adapter import RenderSurface, render_artifact, render_compaction_notice, render_message

__all__ = [
    "RenderSurface",
    "render_message",
    "render_compaction_notice",
    "render_artifact",
]
