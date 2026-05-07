# Marius — Decisions

## Objectif
Construire un socle agentique **modulaire**, **réutilisable** et **fluide**, sans sur-rigidifier la conversation.

## Filiation avec Maurice
Marius conserve l’objectif fonctionnel de Maurice : un assistant agentique utile, capable d’exécuter des tâches et d’interagir de façon conversationnelle. La différence porte surtout sur l’exécution, l’architecture et la modularité, pas sur la finalité produit.

## Identité du nouveau projet
- Nouveau repo / nouveau package.
- Même intention produit, mais approche radicalement différente.
- Nom du projet : **Marius**.

## Surfaces et session canonique
- En mode global, une session canonique commune relie CLI, web et Telegram.
- En mode local, il n’y a pas de session canonique ni de Telegram.
- `marius` lancé sans précision amène à la session canonique côté CLI seulement quand le mode global est actif.
- Les lancements ciblés créent des branches secondaires.
- Les branches sont jetables et servent un dossier / projet précis.
- En mode global, le web peut aussi ouvrir des branches ciblées.
- Les branches peuvent notifier la session canonique.
- La session canonique est la référence pour les notifications et le suivi central en mode global.

## Mode local et mode global
- **Mode local** : l’instance est attachée au dossier de lancement.
- **Mode global** : l’instance vit hors du dossier, avec mémoire générale séparée.
- En mode global, on peut toujours lancer une branche ciblée sur un dossier.
- En mode local, on ne doit pas retomber dans un basculement implicite vers le global.
- L’inverse n’est pas vrai : le mode local ne se comporte pas comme le mode global.

## Projet actif et stratégie de contexte
- En mode local, le projet actif est le dossier de lancement.
- En mode global, le projet actif peut être changé à la demande sur la session canonique.
- Les branches secondaires gardent leur propre mémoire projet.
- Les projets cités restent des références tant qu’un basculement explicite n’a pas eu lieu.
- Le système doit exploiter la compréhension d’intention du LLM plutôt qu’un code agressif et rigide.

## Principe de mémoire des branches
- Une branche secondaire se base uniquement sur sa mémoire projet.
- Elle ne doit pas contaminer la session canonique par défaut.
- La canonique et les branches sont reliées comme surfaces de communication, pas comme un seul bloc de contexte mélangé.

## Initialisation du mode global
- L’assistant demande au premier setup : nom de l’utilisateur, son propre nom, style d’interaction, langue, et emplacement du workspace.
- La mémoire générale vit hors du dossier de travail.
- Le setup doit permettre de distinguer clairement mémoire locale et mémoire globale.

## Nomenclature recommandée

- **Agent** : Marius, l’identité du système.
- **Session canonique** : la session centrale globale, unique en mode global.
- **Session projet** : une session locale ou ciblée, attachée à un projet ou un dossier.
- **Branche** : une session secondaire jetable, rattachée à un projet précis.
- **Workspace** : la mémoire générale hors du dossier en mode global.
- **Project root** : la mémoire locale d’un dossier en mode local.

Règle de base : une session est un point de vue, une branche est un point de vue ciblé, et la session canonique est le point de vue central global.

## Principes non négociables

1. **Le LLM orchestre les outils.**
   - Les outils servent le LLM.
   - Les outils ne doivent pas prendre la main sur la réponse finale, sauf cas exceptionnel de sécurité.

2. **La sécurité passe avant l’exécution.**
   - Un gardien de sécurité agit comme filtre / man-in-the-middle.
   - Il peut autoriser, bloquer ou demander confirmation.
   - Il ne remplace pas le LLM dans l’échange avec l’utilisateur.

3. **Les briques doivent être standalone.**
   - Chaque brique doit pouvoir être réutilisée dans un autre projet.
   - Chaque brique doit être testable seule.
   - Le couplage au reste de Marius doit rester faible.

4. **Le contexte se déclare en Markdown.**
   - Les intentions, décisions et repères projet vivent dans des `.md`.
   - Le code gère l’exécution, pas toute la connaissance du projet.
   - Le Markdown doit rester un format de rendu cohérent entre CLI, web et Telegram.
   - La compaction ne doit jamais supprimer l’historique visible de l’utilisateur ; elle ne compacte que le contexte interne ou les résumés dérivés.
   - Les diffs du workflow dev/self-update doivent rester exposables en Markdown et réinjectables dans l’historique de discussion.

5. **Le projet actif est explicite, mais avec une stratégie claire.**
   - Un autre projet cité n’implique pas automatiquement un changement de contexte.
   - Le système ne doit pas deviner agressivement.
   - Le projet actif doit être défini par une règle simple, visible et stable.

6. **Moins d’outils, mieux choisis.**
   - La surface d’outils doit rester minimale.
   - Chaque outil doit avoir une utilité claire et fréquente.
   - Éviter les outils qui cassent la fluidité ou génèrent des sorties sales.

7. **Canaux et notifications partout.**
   - CLI, web et Telegram restent des canaux du produit.
   - La session canonique doit pouvoir recevoir et émettre les notifications.
   - Les branches ciblées peuvent exister en parallèle sans casser ce canal central.
   - Une même conversation doit rester lisible d’un canal à l’autre, avec les artefacts utiles (diffs, notices de compaction) conservés quand ils sont visibles pour l’utilisateur.

8. **Le code doit rester propre, mais pas rigide inutilement.**
   - Éviter la complexité prématurée.
   - Favoriser des abstractions simples et composables.
   - Ne pas déplacer dans le code ce qui peut vivre dans un document.

9. **Le host web doit rester mince.**
   - Le runtime agent reste le centre du système.
   - Le host web/API est une surface d’accès, pas le cœur produit.
   - Aucune dépendance à FastAPI n’est requise tant que les besoins restent couverts par un host plus léger.
   - Le choix d’un framework web doit être justifié par un besoin produit réel, pas par réflexe technique.

## Règles de design

- Le core définit les contrats.
- Les providers se branchent sur le core via adaptateur.
- Les outils sont exposés comme capacités, pas comme réponses autonomes.
- Les modules doivent éviter les dépendances circulaires.
- Les comportements ambigus doivent préférer la clarification à l’inférence.
- Pour le projet actif, le système doit exploiter la compréhension d’intention du LLM plutôt qu’un code agressif et rigide.

## Harnais projet actif

Le projet actif doit suivre une règle simple et lisible :

- un projet courant doit être déclaré ;
- les autres projets restent des références ;
- le basculement de contexte doit être explicite ;
- si c’est ambigu, on demande.

Ce harnais doit rester déclaratif et être porté par les fichiers Markdown, pas par une heuristique de code trop agressive.

## Ce qu’on évite

- Un monolithe où tout dépend de tout.
- Des outils qui répondent directement à la place du LLM.
- Une logique de contexte trop automatique.
- Des mécanismes de sécurité trop bavards.
- Des abstractions qui ne servent qu’un cas unique.

## Mise à jour de ce document
- Toute décision d’architecture durable doit être ajoutée ici.
- Si une règle devient fausse, on la corrige explicitement plutôt que de la laisser dériver.

## 2026-05-07 — Session runtime minimal côté kernel
- Décision : la continuité conversationnelle courte du kernel est portée par une structure de session orientée `turns`, avec rattachement des `ToolResult`, artefacts et résumés dérivés de compaction.
- Alternatives : stocker directement une simple liste plate de messages, ou déléguer entièrement cet état au host/UI.
- Pourquoi : le kernel a besoin d’un état de travail court et réutilisable sans connaître les canaux, mais ne doit pas prendre en charge l’historique visible produit.
- Impact :
  - le kernel peut préparer un contexte provider cohérent sans dépendre de Telegram/web/CLI ;
  - les résumés de compaction restent internes au kernel ;
  - l’historique visible utilisateur doit rester dans `storage/ui_history_store` ou équivalent, hors de cette brique.

## 2026-05-07 — Seuils initiaux de compaction
- Décision : conserver les seuils initiaux hérités du cadrage précédent tant qu’aucune télémétrie Marius ne justifie mieux.
- Valeurs :
  - `trim_threshold = 0.60`
  - `summarize_threshold = 0.75`
  - `reset_threshold = 0.90`
  - `context_window_tokens = 250_000` par défaut
- Pourquoi : ces seuils sont déjà cohérents avec les attentes de compaction progressive sans suppression de l’historique visible.
- Impact : le kernel peut signaler `trim`, `summarize` ou `reset` avec une base explicite et testable ; si un provider expose une fenêtre différente, la fenêtre runtime doit primer sur le défaut statique.

## 2026-05-07 — Répartition des fichiers Markdown de contexte
- Décision : séparer explicitement l’identité de l’agent, le contexte humain durable et le contexte projet.
- Répartition :
  - `SOUL.md` = identité, ton, posture de l’agent ;
  - `USER.md` = contexte humain durable ;
  - `AGENTS.md` = conventions de travail par projet ;
  - `DECISIONS.md` = choix durables ;
  - `ROADMAP.md` = checklist vivante.
- Pourquoi : éviter que `AGENTS.md` devienne un fourre-tout et garder un assemblage de contexte lisible par nature.
- Impact : le futur `context_builder` devra assembler ces couches comme des sources distinctes ; les branches ciblées réutilisent ces conventions sans créer un nouveau type de fichier tant que ce n’est pas nécessaire.
