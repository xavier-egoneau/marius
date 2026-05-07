# Project Context Permissions Slice — Marius

> Mini-plan de slice autonome, TDD-first, commit clair en fin de feature.

## But
Faire évoluer `project_context` pour séparer clairement projet actif et zone allow, en ajoutant les modes de permissions `safe`, `limited`, `power` et la promotion contrôlée d’un projet hors workspace en mode `limited`.

## Contraintes
- `local` garde un projet actif obligatoire.
- `global` garde un projet actif optionnel.
- Le workspace global est une zone allow de base, pas forcément une prison.
- `safe` / `limited` / `power` relèvent des permissions, pas du rendu.
- Le kernel valide et résout; le host fournit l’état persistant (`workspace_root`, `allowed_roots`, demande explicite).
- Ne pas faire de découverte automatique agressive.

## API minimale visée
- `PermissionMode`
- extension de `ProjectContextInput` avec :
  - `permission_mode`
  - `workspace_root`
  - `allowed_roots`
  - `activate_requested_project`
- extension de `ResolvedProjectContext` avec :
  - `allowed_roots`
  - `permission_mode`
  - metadata de promotion

## Cas à couvrir dans les tests
1. `safe` refuse un projet actif hors workspace.
2. `limited` accepte un projet actif déjà dans `allowed_roots`.
3. `limited` refuse un projet actif hors zone si la demande n’est pas explicite.
4. `limited` promeut un projet actif hors workspace si la demande est explicite et l’ajoute aux roots allowées.
5. `power` accepte un projet actif hors workspace sans promotion.
6. `global` sans projet actif reste autorisé.
7. Les projets cités n’injectent toujours pas leurs documents.
8. Le préambule et les métadonnées reflètent le mode de permissions et la promotion éventuelle.

## Étapes
1. Étendre `tests/kernel/test_project_context.py` avec les cas rouges permissions/allow.
2. Implémenter l’évolution minimale dans `marius/kernel/project_context.py`.
3. Mettre à jour `DECISIONS.md`, `BRICKS.md`, `AGENTS.md`, `ROADMAP.md` pour formaliser les nouveaux invariants.
4. Lancer `pytest tests/kernel/test_project_context.py -q` puis `pytest tests/ -q`.
5. Faire une review ciblée, nettoyer les artefacts, committer.

## Commit prévu
`feat: add permission-aware project context`
