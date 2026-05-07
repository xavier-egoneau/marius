# Marius — Roadmap

## But
Créer une base agentique modulaire, réutilisable et simple à faire évoluer, tout en conservant la finalité fonctionnelle initiale.

## Priorités

### 0. Identité et cadrage
- Poser la finalité produit identique et l’approche de réécriture radicalement différente.
- Définir clairement les deux modes : local et global.
- Définir le setup initial du mode global : nom utilisateur, nom de l’assistant, style d’interaction, langue, workspace.

### 1. Fondations
- Définir les contrats du core.
- Définir le flux de requête.
- Définir les interfaces entre core, provider, guard, tools, sessions et contexte.
- Stabiliser la liste des briques standalone dans `BRICKS.md`.

### 2. Session canonique et branches
- Définir la session canonique commune CLI/web/Telegram en mode global seulement.
- Définir le comportement des branches ciblées par dossier.
- Définir les règles de mémoire locale des branches.
- Définir l’absence de session canonique et de Telegram en mode local.
- Définir l’ouverture de branches ciblées depuis le web en mode global.
- Définir les notifications de branche vers la session canonique.

### 3. Brique provider
- Ajouter un adaptateur minimal vers les providers.
- Normaliser l’appel, l’auth, le streaming et les erreurs.
- Garder cette brique standalone.

### 4. Gardien de sécurité
- Intercepter les actions sensibles.
- Autoriser / bloquer / demander confirmation.
- Éviter toute surcharge de verbosité.

### 5. Contexte Markdown
- Définir les fichiers `.md` source de vérité.
- Formaliser le projet actif avec une stratégie explicite.
- Séparer intention, mémoire et décisions.
- Définir explicitement la place de `SOUL.md`, `USER.md`, `AGENTS.md`, `DECISIONS.md` et `ROADMAP.md`.
- Garantir un rendu Markdown cohérent entre CLI, web et Telegram.
- Préserver l’historique visible de l’utilisateur même quand le contexte interne est compacté.
- Rendre les diffs de développement lisibles et réutilisables dans les surfaces de discussion.

### 6. Skills, dreaming et daily
- Définir le store de skills partagé.
- Définir l’activation des skills par agent.
- Définir les apports `dream.md` / `daily.md` au dreaming et au digest.

### 7. Canaux
- Définir CLI, web et Telegram comme canaux du produit.
- Définir les règles de notifications entre surfaces.
- Définir comment une même conversation reste lisible d’un canal à l’autre, sans casser le format Markdown.
- Définir comment les artefacts de type diff et les notices de compaction se propagent entre surfaces.
- Garder le host web/API suffisamment mince pour ne pas faire dériver le cœur du produit vers une architecture web-first.

### 8. Tests et stabilité
- Tester chaque brique isolément.
- Vérifier l’absence de couplage fort.
- Valider la fluidité des réponses.

## Règle de conduite
Avant d’implémenter une nouvelle fonctionnalité, vérifier :
- est-ce une brique réutilisable ?
- est-ce standalone ?
- est-ce vraiment nécessaire maintenant ?
- est-ce que ça améliore la fluidité ?

## État actuel
- Architecture définie sur le principe : LLM au centre, guard de sécurité, outils minimaux, contexte en Markdown.
- Le socle doit aussi préserver l’historique utilisateur, même si le contexte interne est compacté ou réécrit.
- Les flux dev/self-update doivent exposer les diffs proprement dans l’UI et dans les messages.
- Liste détaillée des briques à définir ensuite.

## Slices d’implémentation en cours
- [x] Cadrer la répartition des fichiers Markdown de contexte (`SOUL.md`, `USER.md`, `AGENTS.md`, `DECISIONS.md`, `ROADMAP.md`) [serial] [high]
- [x] Poser les frontières `kernel` / `host` / `render` / `storage` dans la doc [serial] [high]
- [x] Créer le squelette Python minimal des couches principales [serial] [high]
- [x] Ajouter une première brique `session_runtime` orientée tours et indépendante des canaux [serial] [high]
- [x] Ajouter des tests kernel pour compaction, session runtime et orchestrateur minimal [serial] [high]
- [x] Brancher un `provider_adapter` minimal sur le `runtime_orchestrator` [serial] [high]
- [x] Introduire un `ui_history_store` concret distinct du contexte interne [serial] [high]
- [x] Poser un `render_adapter` Markdown cross-canaux pour messages, notices et diffs [serial] [high]
- [x] Ajouter un `context_builder` minimal pour assembler explicitement les sources Markdown de contexte [serial] [high]
- [x] Ajouter un `project_context` minimal pour résoudre le projet actif et préparer les sources du `context_builder` [serial] [high]
