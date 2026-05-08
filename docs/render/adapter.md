# render_adapter

## Rôle

Transforme les objets du kernel (messages, artefacts, notices de compaction) en Markdown portable. Point de départ pour tout rendu visible — CLI, web, Telegram partagent la même sortie tant qu'aucune divergence produit ne l'impose.

## Couche

Render

## Standalone

Oui. Dépend uniquement des contrats kernel.

## Dépendances

- `marius.kernel.contracts` — `Message`, `Artifact`, `ArtifactType`, `CompactionNotice`

## Interface publique

```python
def render_message(message: Message) -> str
    # Retourne le contenu texte du message, prêt à afficher.
    # Messages non visibles (visible=False) → chaîne vide.

def render_compaction_notice(notice: CompactionNotice) -> str
    # Retourne une notice lisible sur le niveau de compaction atteint.
    # Ex : "[ contexte compacté — niveau : trim ]"

def render_artifact(artifact: Artifact) -> str
    # DIFF    → rendu détaillé avec blocs de code
    # Autres  → fallback portable (type + path)
```

## Usage

```python
from marius.render.adapter import render_message, render_artifact, render_compaction_notice
from marius.kernel.contracts import Message, Role, Artifact, ArtifactType, CompactionNotice
from datetime import datetime, timezone

msg = Message(role=Role.ASSISTANT, content="Voici la réponse.", created_at=datetime.now(timezone.utc))
print(render_message(msg))
# → "Voici la réponse."

notice = CompactionNotice(level="trim", summary="Contexte réduit.")
print(render_compaction_notice(notice))
# → "[ contexte compacté — niveau : trim ]"

diff = Artifact(type=ArtifactType.DIFF, path="patch.diff", data={"content": "--- a\n+++ b\n..."})
print(render_artifact(diff))
# → bloc de code diff formaté
```

## Surfaces futures

Quand un besoin produit impose une divergence, des variantes `render_message_cli()`, `render_message_telegram()`, etc. peuvent coexister. La sortie `portable` reste la base commune.

## Invariants

- Un message `visible=False` retourne une chaîne vide — il n'est jamais affiché à l'utilisateur.
- Les artefacts `DIFF` ont un rendu détaillé ; les autres ont toujours un fallback lisible.
- Cette brique ne connaît ni sécurité, ni persistance, ni sélection de projet.
