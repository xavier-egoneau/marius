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

## 2026-05-07 — Provider adapter minimal
- Décision : introduire d’abord un contrat provider synchrone minimal, injectable dans le runtime, avant tout streaming ou toute logique de retry avancée.
- Contrat minimal :
  - `ProviderRequest` reçoit des `Message` structurés ;
  - `ProviderResponse` renvoie un `Message` assistant structuré et une `ContextUsage` ;
  - `ProviderError` normalise au moins `provider_name` et `retryable`.
- Pourquoi : valider vite l’interface entre runtime et providers sans figer trop tôt une API plus complexe.
- Impact :
  - `runtime_orchestrator` peut fonctionner soit en préparation de contexte seule, soit avec un provider injecté ;
  - le streaming, les retries et l’appel réseau réel restent des slices ultérieurs ;
  - la brique reste testable avec un double en mémoire.

## 2026-05-07 — Render adapter minimal
- Décision : introduire d’abord un `render_adapter` qui retourne un Markdown portable (`str`) à partir des contrats kernel, avant tout rendu structuré spécifique au web ou à Telegram.
- Portée minimale :
  - `render_message(...)` pour le contenu principal ;
  - `render_compaction_notice(...)` pour les notices utiles ;
  - `render_artifact(...)` pour les artefacts `diff`.
- Pourquoi : matérialiser vite la frontière `render` sans choisir trop tôt une UI riche ni un framework web.
- Impact :
  - le host peut rester mince en consommant un texte déjà rendu ;
  - les surfaces `portable`, `cli`, `telegram` et `web` partagent la même sortie tant qu’un besoin produit n’impose pas de divergence ;
  - les artefacts `diff` reçoivent un rendu détaillé, les autres artefacts un fallback portable visible.

## 2026-05-07 — Context builder minimal
- Décision : introduire un `context_builder` kernel qui assemble des sources Markdown explicites en un `system_prompt` déterministe, sans découverte automatique de projet.
- Contrat minimal :
  - `ContextSource` décrit une source (`key`, `title`, `path`, `required`) ;
  - `ContextBuildInput` porte un `preamble` et une liste ordonnée de sources ;
  - `ContextBundle` renvoie le Markdown assemblé, les sources chargées et les sources optionnelles manquantes.
- Pourquoi : matérialiser l’assemblage du contexte sans glisser trop tôt vers `project_context`, le host ou une heuristique de navigation repo.
- Impact :
  - le host ou une future brique `project_context` choisira les chemins ;
  - le runtime peut continuer à injecter le résultat via `TurnInput.system_prompt` sans changer son contrat ;
  - une source requise absente casse le build explicitement, une source optionnelle absente reste traçable.

## 2026-05-07 — Project context minimal
- Décision : introduire un `project_context` kernel qui résout explicitement le projet actif, les projets cités et le scope de session (`canonical`, `project`, `branch`) avant l’assemblage Markdown.
- Contrat minimal :
  - `ProjectContextInput` porte `mode`, `session_scope`, `active_project`, `cited_projects` et éventuellement une `branch` ;
  - `ResolvedProjectContext` renvoie un `preamble`, un `ContextBuildInput` et des métadonnées stables ;
  - un `ProjectCatalog` abstrait fournit uniquement les chemins documentaires du projet actif.
- Pourquoi : matérialiser la règle du projet actif sans l’enterrer dans le host et sans faire dériver `context_builder` vers une logique de sélection projet.
- Impact :
  - en mode `local`, un projet actif est requis ;
  - une branche ciblée exige un projet actif explicite et un identifiant de branche ;
  - en mode `global`, l’absence de projet actif reste autorisée tant qu’aucun projet n’est fixé ;
  - seuls les documents du projet actif alimentent le `context_builder`, les projets cités restant des références visibles dans le préambule.

## 2026-05-07 — Project context permission-aware
- Décision : étendre `project_context` avec une séparation explicite entre projet actif et zone allow, pilotée par les modes `safe`, `limited` et `power`.
- Contrat minimal :
  - `ProjectContextInput` porte aussi `permission_mode`, `workspace_root`, `allowed_roots` et un signal `activate_requested_project` ;
  - `ResolvedProjectContext` renvoie les roots allowées effectives et signale si le projet actif a été promu dans la zone allow ;
  - `ProjectCatalog` reste limité aux chemins documentaires, sans logique de permissions.
- Pourquoi : le workspace global est une zone allow de base, mais il ne doit pas être confondu avec le projet actif ni devenir une prison unique dans tous les modes.
- Impact :
  - `safe` impose que le projet actif reste dans la zone allow actuelle ;
  - `limited` autorise la promotion explicite d’un projet hors workspace et l’ajoute aux roots allowées ;
  - `power` accepte un projet actif hors workspace sans promotion préalable ;
  - un scope `project` exige un projet actif ;
  - un objet `branch` n’est valide qu’avec le scope `branch` ;
  - les chemins documentaires renvoyés pour le projet actif doivent rester sous sa root ;
  - les projets cités restent des références de contexte, pas des extensions implicites de permissions.

## 2026-05-07 — Guardian policy minimale pour l’extension d’allow
- Décision : extraire hors de `project_context` la décision d’extension de la zone allow dans une brique `guardian_policy` pure et synchrone.
- Contrat minimal :
  - `GuardianPolicy.review_allow_expansion(request)` reçoit uniquement le mode de permission, la zone allow actuelle, la root candidate, le workspace éventuel et le signal d’explicitation utilisateur ;
  - `AllowExpansionDecision` renvoie un statut `not_required` / `allow` / `deny` / `ask`, un `code` stable et les `roots_to_add` exactes quand une extension est accordée ;
  - `project_context` garde la normalisation des paths, la résolution du projet actif et l’application mécanique de la décision, sans réimplémenter la politique.
- Pourquoi : empêcher qu’une promotion hors allow soit décidée implicitement par le résolveur de contexte, et garder une politique de sécurité standalone, testable et réutilisable.
- Impact :
  - aucune mutation de l’allow-list ne doit arriver sans décision explicite `allow` ;
  - quand aucune zone allow de base n’est déclarée, le gardien ne bloque pas inutilement le simple contexte projet : il ne mutera pas l’allow-list tant qu’il n’a rien à étendre ;
  - `project_context` peut lever une erreur métier stable sur `ask` ou `deny` sans fabriquer lui-même la règle ;
  - le mode `power` reste un droit d’usage sans auto-extension de l’allow-list ;
  - la largeur acceptable d’une root candidate devient une responsabilité du gardien ;
  - les métadonnées de résolution doivent progressivement préférer un triplet générique `allow_expansion_status` / `allow_expansion_code` / `allow_expansion_roots` au simple booléen `active_project_promoted`.
