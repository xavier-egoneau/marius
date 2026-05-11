# render_adapter

## Rôle

Transforme les objets du kernel (messages, résultats outils, artefacts, notices de compaction) en Markdown portable. Point de départ pour tout rendu visible — CLI, web, Telegram partagent la même sortie tant qu'aucune divergence produit ne l'impose.

## Couche

Render

## Standalone

Oui. Dépend uniquement des contrats kernel.

## Dépendances

- `marius.kernel.contracts` — `Message`, `ToolResult`, `Artifact`, `ArtifactType`, `CompactionNotice`

## Interface publique

```python
def render_message(message: Message) -> str
    # Retourne le contenu texte du message, prêt à afficher.
    # Messages non visibles (visible=False) → chaîne vide.

def render_turn_output(
    assistant_message: Message | None,
    *,
    tool_results: list[ToolResult] | None = None,
    compaction_notice: CompactionNotice | None = None,
) -> str
    # Retourne la sortie visible de fin de tour :
    # réponse assistant + artefacts outils + notice kernel éventuelle.

def render_compaction_notice(notice: CompactionNotice) -> str
    # Retourne une notice lisible sur le niveau de compaction atteint.
    # Ex : "[ contexte compacté — niveau : trim ]"

def render_artifact(artifact: Artifact) -> str
    # DIFF    → rendu détaillé avec blocs de code
    # REPORT avec data.content → rendu Markdown détaillé
    # Autres  → fallback portable (type + path)

def render_artifacts(artifacts: list[Artifact]) -> str
    # Retourne une suite d'artefacts dédupliqués.
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

Le paramètre `surface` accepte déjà `portable`, `cli`, `web` et `telegram`. La première version garde volontairement la même sortie Markdown partout. Quand un besoin produit impose une divergence, des variantes de rendu peuvent coexister, mais la sortie `portable` reste la base commune.

Les canaux gardent leurs adaptations finales :
- CLI : rendu via `rich.markdown.Markdown`.
- Web : renderer Markdown inline sans dépendance externe, appliqué en fin de streaming.
- Telegram : conversion Markdown basique vers HTML Telegram, avec découpe qui garde les blocs de code équilibrés.

## Invariants

- Un message `visible=False` retourne une chaîne vide — il n'est jamais affiché à l'utilisateur.
- Les outils ne répondent pas à la place du LLM : leurs artefacts sont ajoutés comme pièces visibles de fin de tour.
- Les artefacts `DIFF` ont un rendu détaillé.
- Les artefacts `REPORT` avec contenu Markdown (`data.content`) sont rendus en détail ; sans contenu, ils gardent un fallback lisible.
- Les artefacts identiques sont dédupliqués avant affichage.
- Cette brique ne connaît ni sécurité, ni persistance, ni sélection de projet.
