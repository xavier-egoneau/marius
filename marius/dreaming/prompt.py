"""Construction des prompts pour le dreaming et le daily."""

from __future__ import annotations

from __future__ import annotations

from typing import Any

from .context import DreamingContext
from marius.storage.memory_store import MemoryEntry


def build_dreaming_prompt(ctx: DreamingContext) -> str:
    """Construit le system prompt pour l'appel LLM dreaming."""
    parts: list[str] = []

    parts.append(
        "Tu es le processus de consolidation mémorielle de Marius.\n"
        "Ta mission : maintenir une mémoire longue de qualité — pertinente, à jour, sans redondance.\n"
        "\n"
        "Analyse tout ce que tu vois et décide des opérations à effectuer.\n"
        "Réponds UNIQUEMENT avec un objet JSON valide. Aucun texte avant ou après."
    )

    # Mémoire actuelle
    if ctx.memories:
        parts.append(_format_memories_section(ctx.memories))
    else:
        parts.append("## Mémoire actuelle\n(aucun souvenir enregistré)")

    # Sessions récentes
    if ctx.session_summaries:
        parts.append(
            "## Sessions récentes (métadonnées)\n"
            + "\n".join(ctx.session_summaries)
        )

    # Contrats de rêverie
    if ctx.dream_contracts:
        contracts_text = "\n\n".join(
            f"### Contrat [{name}]\n{content}"
            for name, content in ctx.dream_contracts
        )
        parts.append(f"## Contrats de rêverie\n{contracts_text}")

    # Documents projet
    if ctx.decisions_doc:
        parts.append(f"## DECISIONS.md\n{ctx.decisions_doc}")
    if ctx.roadmap_doc:
        # Limiter la roadmap pour ne pas saturer le contexte
        roadmap = ctx.roadmap_doc[:4000]
        if len(ctx.roadmap_doc) > 4000:
            roadmap += "\n[...tronqué]"
        parts.append(f"## ROADMAP.md\n{roadmap}")

    # Format de sortie
    parts.append(_DREAMING_OUTPUT_FORMAT)

    return "\n\n".join(parts)


def build_daily_prompt(ctx: DreamingContext, last_dream_report: "Any | None" = None) -> str:
    """Construit le system prompt pour l'appel LLM daily."""
    parts: list[str] = []

    parts.append(
        "Tu es le processus de briefing quotidien de Marius.\n"
        "Ta mission : générer un briefing de début de journée clair et actionnable.\n"
        "Réponds en Markdown structuré."
    )

    # Dernier rapport de dream si disponible
    if last_dream_report is not None:
        parts.append(
            f"## Dernier dreaming ({last_dream_report.generated_at[:16]})\n"
            f"- {last_dream_report.added} souvenir(s) ajouté(s), "
            f"{last_dream_report.updated} mis à jour, "
            f"{last_dream_report.removed} supprimé(s)\n"
            f"- Résumé : {last_dream_report.summary}"
        )

    if ctx.memories:
        parts.append(_format_memories_section(ctx.memories))

    if ctx.daily_contracts:
        contracts_text = "\n\n".join(
            f"### Contrat [{name}]\n{content}"
            for name, content in ctx.daily_contracts
        )
        parts.append(f"## Contrats daily\n{contracts_text}")
    else:
        parts.append(
            "## Contrats daily\n"
            "(aucun contrat daily actif — génère un briefing général "
            "basé sur la mémoire disponible)"
        )

    return "\n\n".join(parts)


# ── helpers ───────────────────────────────────────────────────────────────────


def _format_memories_section(memories: list[MemoryEntry]) -> str:
    lines: list[str] = [f"## Mémoire actuelle ({len(memories)} souvenirs)"]
    for m in memories:
        scope_label = f"[{m.scope}]"
        if m.scope == "project" and m.project_path:
            scope_label = f"[project: {m.project_path}]"
        tag_label = f" [{m.tags}]" if m.tags else ""
        lines.append(f"#{m.id} {scope_label}{tag_label} : {m.content}")
    return "\n".join(lines)


_DREAMING_OUTPUT_FORMAT = """\
## Format de sortie

```json
{
  "operations": [
    {"op": "add",     "content": "...", "scope": "global", "tags": "..."},
    {"op": "add",     "content": "...", "scope": "project", "project_path": "/chemin", "tags": "..."},
    {"op": "replace", "old": "<extrait exact du contenu actuel>", "new": "..."},
    {"op": "remove",  "text": "<extrait exact du contenu actuel>"}
  ],
  "summary": "Bilan : X ajoutés, Y mis à jour, Z supprimés."
}
```

Règles :
- `old` et `text` doivent correspondre à un extrait exact d'un souvenir existant.
- `scope` vaut `global` (toujours injecté) ou `project` (injecté dans le contexte du projet).
- Si rien à faire : `{"operations": [], "summary": "Mémoire à jour."}`.
- Aucun texte avant ou après le JSON."""
