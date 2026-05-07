# Mini-plan — context_builder minimal

## Objectif
Poser une première brique `context_builder` standalone qui assemble explicitement les sources Markdown de contexte en un `system_prompt` déterministe, sans découverte automatique de projet ni couplage au host.

## Contraintes
- Le kernel peut assembler le contexte logique, mais ne choisit pas lui-même le projet actif.
- Les sources sont injectées explicitement et l’ordre est déclaratif.
- Les sources requises doivent échouer bruyamment si absentes.
- Les sources optionnelles absentes doivent être tracées sans casser le build.
- Le résultat doit rester directement injectable dans `TurnInput.system_prompt`.

## Tâches
1. **TDD context_builder** [serial]
   - Créer `tests/kernel/test_context_builder.py`.
   - Couvrir : ordre des sections, required manquant, optional manquant, omission des sections vides, métadonnées de sources chargées.

2. **Implémentation kernel** [serial]
   - Créer `marius/kernel/context_builder.py`.
   - Ajouter : `MarkdownSourceReader`, `ContextSource`, `ContextBuildInput`, `ContextBundle`, `MissingContextSourceError`, `ContextBuilder`.
   - Exporter l’API via `marius/kernel/__init__.py`.

3. **Intégration légère** [serial]
   - Garder l’intégration au runtime indirecte via `system_prompt: str` existant, sans changer `runtime.py` dans cette slice.

4. **Cohérence docs** [parallélisable après 2]
   - Mettre à jour `ROADMAP.md`, `DECISIONS.md`, `AGENTS.md`, `BRICKS.md` pour expliciter la portée minimale et la non-découverte automatique.

5. **Review & validation** [serial]
   - Review spec + qualité.
   - Lancer `pytest tests/ -q`.
   - Commit clair.

## Arbitrages retenus
- Le builder reste dans le kernel.
- Pas de scan filesystem ni de logique `project_context` dans cette slice.
- Pas de skills, mémoire ou historique injectés automatiquement.
- Le builder produit un Markdown assemblé + métadonnées de traçabilité minimale.