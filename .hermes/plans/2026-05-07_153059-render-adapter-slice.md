# Mini-plan — render_adapter Markdown cross-canaux

## Objectif
Poser une première brique `render_adapter` standalone, testable, qui transforme les contrats kernel en Markdown portable pour les surfaces CLI/web/Telegram, en couvrant uniquement : message principal, notice de compaction, artefact diff.

## Contraintes
- Le kernel reste ignorant des surfaces concrètes.
- Le render retourne du texte Markdown, sans logique réseau/UI riche.
- La première slice reste sync, petite, tolérante et sans sur-abstraction.
- Les diffs sont des artefacts rendus, pas une nouvelle sémantique kernel.

## Tâches
1. **TDD render tests** [serial]
   - Créer `tests/render/test_adapter.py`.
   - Couvrir : message simple, diff inline, notice de compaction, fallback diff sans contenu, surfaces supportées.

2. **Implémentation render** [serial]
   - Créer `marius/render/adapter.py`.
   - Ajouter `RenderSurface`, `render_message`, `render_compaction_notice`, `render_artifact`.
   - Exporter l’API dans `marius/render/__init__.py`.

3. **Cohérence docs** [parallélisable après 2]
   - Mettre à jour `ROADMAP.md`, `DECISIONS.md`, `AGENTS.md`, `BRICKS.md` avec la portée exacte de la slice.

4. **Review & validation** [serial]
   - Faire review spec + qualité.
   - Lancer `pytest tests/ -q`.
   - Commit clair.

## Arbitrages implicites retenus
- Pas de `RenderResult` structuré pour l’instant.
- Pas de troncature configurable ni d’échappement Telegram spécifique v1.
- Même rendu portable pour `portable`, `cli`, `telegram`, `web` tant qu’aucun besoin produit n’impose une divergence.
