# Guardian Policy Slice — Marius

> Mini-plan de slice autonome, TDD-first, commit clair en fin de feature.

## But
Extraire hors de `project_context` la décision d’extension d’allow vers une brique kernel `guardian_policy` minimale, synchrone et testable.

## Intention
- `project_context` garde la résolution du projet actif, la normalisation des paths et la préparation du contexte.
- `guardian_policy` décide `not_required` / `allow` / `deny` / `ask` pour une extension d’allow.
- Aucune mutation de l’allow-list sans décision explicite du gardien.
- Une root trop large ne doit pas devenir allow par simple demande.

## Slices visées
1. Ajouter un module `marius/kernel/guardian_policy.py` avec contrats et politique par défaut.
2. Couvrir la politique en TDD (`tests/kernel/test_guardian_policy.py`).
3. Refactorer `project_context` pour injecter la politique et consommer ses décisions au lieu de promouvoir directement.
4. Étendre les tests de `project_context` sur `allow` / `ask` / `deny` / `not_required`.
5. Mettre à jour les docs si les invariants finaux diffèrent légèrement du cadrage.

## Invariants
- `project_context` n’ajoute que `decision.roots_to_add`.
- `roots_to_add` est vide sauf si `status == allow`.
- `power` n’entraîne pas de mutation implicite.
- `safe` bloque une extension hors zone allow.
- `limited` hors zone allow sans demande explicite passe par `ask`.
- Une root candidate trop large est refusée par le gardien.

## Vérification prévue
- `pytest tests/kernel/test_guardian_policy.py -q`
- `pytest tests/kernel/test_project_context.py -q`
- `pytest tests/ -q`
