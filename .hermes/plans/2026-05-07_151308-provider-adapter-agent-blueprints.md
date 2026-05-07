# Mini-plan — provider adapter + agent blueprints

## Contexte
Le prochain slice utile doit combler deux trous :
1. conventions de contexte Markdown par agent/projet (`SOUL.md`, `USER.md`, `AGENTS.md`, etc.),
2. brique `provider_adapter` minimale branchée au runtime.

## Lecture d’intention retenue
- Maurice séparait clairement l’identité de l’agent (`SOUL.md`), le contexte humain (`USER.md`), le contexte projet (`AGENTS.md`, `DECISIONS.md`) et les apports par skill.
- Maurice ne semblait pas centré sur FastAPI ; le web était un gateway léger au-dessus du runtime, avec SSE et endpoints locaux.
- Pour Marius, l’intention utile à conserver est la séparation des responsabilités et un host web mince, pas la copie technique.

## Tâches

### T1 — Cadrage documentaire [serial] [high]
- Ajouter les décisions manquantes sur :
  - fichiers Markdown par agent/projet,
  - place de `SOUL.md` / `USER.md`,
  - host web mince et non framework-centric,
  - non-obligation de FastAPI à ce stade.
- Mettre à jour `ROADMAP.md`, `DECISIONS.md`, `AGENTS.md`, `BRICKS.md` si nécessaire.

### T2 — Provider adapter minimal [serial] [high]
- Écrire les tests en premier.
- Introduire un contrat provider minimal :
  - génération synchrone,
  - message assistant structuré,
  - usage/tokens remontés,
  - erreur provider normalisée.
- Brancher le provider dans `RuntimeOrchestrator` avec injection simple.

### T3 — Vérification [serial] [high]
- Lancer `pytest tests/ -q`.
- Vérifier la cohérence docs/code.
- Commit clair pour chaque feature terminée.

## Parallélisable
- La recherche d’intention Maurice sur agent files et web host peut être faite en parallèle du cadrage ; elle a déjà été réalisée.

## Risques
- Sur-concevoir trop tôt la partie provider (streaming, retry, tools) au lieu de garder un noyau minimal.
- Mélanger les responsabilités de `context_builder`, `provider_adapter` et `runtime_orchestrator`.

## Règle
- Garder le slice petit : génération synchrone minimale d’abord, streaming plus tard.
