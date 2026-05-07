# Project Context Slice — Marius

> Mini-plan de slice autonome, TDD-first, commit clair en fin de feature.

## But
Ajouter une brique `project_context` standalone qui choisit le projet actif et prépare des sources explicites pour `context_builder`, sans mettre cette logique dans le host.

## Contraintes
- Respecter la séparation `kernel / host / render / storage`.
- Ne pas faire de découverte automatique agressive du projet actif.
- Distinguer clairement projet actif et projets cités.
- Respecter les règles `local` / `global` et le cas de branche ciblée.
- Produire une sortie testable réutilisable par `context_builder`.

## API minimale visée
- `RuntimeMode`
- `SessionScope`
- `ProjectRef`
- `BranchRef`
- `ProjectDocumentPaths`
- `ProjectContextInput`
- `ResolvedProjectContext`
- `ProjectCatalog` (protocol)
- `ProjectContextResolver`

## Étapes
1. Écrire les tests rouges sur les invariants et la résolution minimale.
2. Implémenter le module `marius/kernel/project_context.py` avec une API déterministe et un pont vers `ContextBuildInput`.
3. Vérifier que seuls les fichiers du projet actif sont injectés comme `ContextSource`.
4. Mettre à jour `ROADMAP.md`, `DECISIONS.md`, `AGENTS.md`, `BRICKS.md` si le slice fixe de nouvelles règles explicites.
5. Lancer `pytest tests/ -q`, faire une review rapide, nettoyer, committer.

## Cas à couvrir dans les tests
- mode `local` requiert un projet actif ;
- une branche ciblée requiert un projet actif ;
- un projet actif ne peut pas aussi être cité ;
- en mode `global`, aucun projet actif est autorisé ;
- les sources du `ContextBuildInput` ne viennent que du projet actif ;
- l’ordre des sources est stable : `AGENTS`, `DECISIONS`, `ROADMAP` ;
- le préambule mentionne mode, projet actif, projets cités et branche ciblée si présente.

## Commit prévu
`feat: add project context resolver`
