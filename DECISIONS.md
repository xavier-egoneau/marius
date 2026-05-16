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

## 2026-05-15 — Synchronisation live canonique des surfaces

Le gateway est la source canonique de l'historique visible et du flux live entre
CLI, web, routines et Telegram.

Implémentation :
- chaque entrée visible utilisateur/assistant est écrite par le gateway dans
  l'historique canonique ;
- le gateway publie ensuite un événement `visible` aux clients connectés ;
- `/new` archive et vide l'historique visible côté gateway, puis publie
  `visible_reset` ;
- le host web relaie ces événements vers le navigateur via SSE et ne maintient
  plus sa propre vérité d'historique ;
- Telegram reçoit les entrées visibles non-Telegram depuis ce même flux, sans
  miroir de tour reconstitué.

Conséquences :
- les surfaces doivent converger par événements live, pas par polling périodique ;
- le fichier d'historique reste une persistance et une source de rattrapage,
  pas le mécanisme de synchronisation principal ;
- une compaction (`/compact`) peut modifier le contexte interne sans supprimer
  l'historique visible utilisateur.

## 2026-05-15 — Prompts de routine non visibles

Les routines envoient bien leur prompt au runtime LLM, mais ce prompt est une
instruction planifiée et non un message utilisateur à afficher tel quel dans la
conversation canonique.

Conséquences :
- le channel `routine` masque l'entrée utilisateur dans l'historique visible ;
- la réponse assistant de la routine reste visible et synchronisée sur les
  surfaces canoniques ;
- le prompt reste conservé dans la définition de la routine et dans le contexte
  runtime du tour, mais n'encombre pas le chat quotidien.

## 2026-05-16 — Retry streaming avant première sortie visible

Les erreurs provider marquées `retryable` doivent être retentées aussi en mode
streaming tant qu'aucun delta texte n'a été envoyé au client.

Conséquences :
- un 429/5xx ou une coupure réseau à l'ouverture du stream ne fait pas échouer
  le tour immédiatement ;
- après le premier delta texte visible, le runtime ne relance pas la requête
  pour éviter de dupliquer une réponse déjà streamée ;
- la même règle s'applique aux réponses finales forcées par le runtime.

## 2026-05-16 — Permissions héritées par les subagents

Un worker `spawn_agent` hérite des racines de lecture/écriture autorisées du
parent, notamment le projet actif explicitement validé.

Conséquences :
- un subagent en mode `limited` peut lire le projet actif même si le gateway
  tourne depuis le workspace global `~/.marius/workspace/<agent>` ;
- les workers restent non interactifs : une permission hors zone continue
  d'être refusée automatiquement ;
- un worker bloqué par une permission remonte une `permission_requests`
  structurée au parent ; le parent est responsable de l'ask utilisateur et de
  la reprise éventuelle ;
- le timeout demandé par le modèle pour un worker est borné à un minimum stable
  afin d'éviter des expirations immédiates sur les tâches planifiées ;
- le prompt worker expose le workspace courant et les racines autorisées pour
  éviter les conclusions spéculatives sur le contexte projet.

## 2026-05-16 — Outils explicites de gestion des racines autorisées

La liste blanche fichier reste une brique système persistée dans
`~/.marius/allowed_roots.json`, mais elle est maintenant pilotable par outils :
`allow_root_list`, `allow_root_add` et `allow_root_remove`.

Conséquences :
- le LLM peut répondre à une demande naturelle du type "autorise ce dossier"
  sans détour par un changement de projet ;
- ajouter une racine est traité comme une extension de confiance et passe par le
  gardien de permissions ;
- les racines système, `/`, le home entier et les racines trop larges sont
  refusées, tandis que les grands dossiers utilisateur comme `~/Documents`
  déclenchent une confirmation explicite ;
- retirer une racine est une action de réduction de confiance et reste
  autorisée directement par le guard.

## 2026-05-16 — Ask permission global et promotion en racine autorisée

Une demande de permission interactive appartient au gateway, pas à une surface
particulière.

Conséquences :
- le gateway garde les demandes de permission en attente et les relaie aux
  surfaces connectées ;
- une surface qui se connecte pendant qu'une demande est en attente reçoit aussi
  la demande, afin d'éviter les blocages silencieux ;
- les tours déclenchés depuis Telegram ou depuis une task peuvent produire un
  ask visible sur les surfaces web/CLI ;
- Telegram affiche aussi des boutons inline `Autoriser` / `Refuser` pour
  répondre directement à l'ask depuis le chat ;
- les tours Telegram lancés depuis le poller tournent en arrière-plan afin que
  le même poller puisse continuer à recevoir les callbacks de permission ;
- une approbation utilisateur ne valide pas seulement l'appel en cours : pour
  les opérations filesystem/RAG/projet, le dossier pertinent est promu dans
  `~/.marius/allowed_roots.json` après revue du gardien ;
- les ajouts de racines depuis le dashboard passent par la même politique de
  gardien avant de modifier la liste blanche.

## 2026-05-16 — PermissionGuard deny-by-default

Le gardien de permissions refuse désormais les outils non classés explicitement.

Conséquences :
- ajouter un nouvel outil runtime exige de le classer dans le guard : read-only,
  filesystem, admin sensible, orchestration interne, etc. ;
- un oubli de classification se transforme en refus visible plutôt qu'en accès
  implicite ;
- les outils d'orchestration Marius (`task_*`, `reminders`, `spawn_agent`,
  `call_agent`, `open_marius_web`) sont classés explicitement comme capacités
  autorisées quand elles sont exposées à l'agent par la configuration.

## 2026-05-16 — Projet actif souple et contexte déterministe des tasks

Le projet actif reste fluide en conversation, mais déterministe pendant
l'exécution d'une task.

Conséquences :
- en conversation normale, l'agent conserve ou change le projet actif selon
  l'intention utilisateur ; s'il y a ambiguïté entre le projet actif et un autre
  projet cité, il demande confirmation ;
- une task unique qui porte un `project_path` impose ce dossier comme projet
  actif d'exécution pour le tour task ;
- une demande naturelle de création de nouveau projet doit devenir une task
  Kanban par défaut, assignée à l'agent courant ;
- une task avec `project_path='nouveau'` commence volontairement sans projet
  actif réel : elle crée d'abord le dossier, puis remplace `project_path` par le
  chemin absolu réel ;
- créer un nouveau projet ne force pas le projet actif global si la demande
  s'arrête à la création du dossier ; l'agent active le nouveau projet seulement
  si la task demande de travailler dedans après création ;
- le dashboard ne pré-crée pas le dossier d'un nouveau projet à la place de la
  task : la création passe par les outils de l'agent et donc par le gardien.

## 2026-05-16 — Dashboard mince par extraction progressive

Le dashboard peut rester une surface humaine/admin riche, mais sa logique métier
ne doit pas devenir une vérité concurrente du runtime.

Conséquences :
- les règles durables du Task Board, des projets, des racines autorisées et des
  routines doivent migrer progressivement vers des services backend testables ;
- le dashboard doit se limiter à valider/normaliser les entrées HTTP, appeler ces
  services, puis rendre leur résultat ;
- les comportements déjà extraits (`task_execution_message`, guard allow-roots,
  task store/scheduler) servent de modèle pour les extractions suivantes ;
- on évite une réécriture large : chaque déplacement se fait au moment où une
  règle métier est touchée ou testée.

## 2026-05-16 — Workflows dev pilotés par le Task Board

Les commandes de développement `/plan`, `/dev`, `/resume`, `/check` et `/pr`
doivent utiliser le Task Board comme source de vérité du suivi.

Conséquences :
- `/plan` crée des cards Kanban via `task_create`, avec dépendances,
  parallélisme, critères d'acceptation et `project_path` dans le prompt de la
  task ;
- `/dev` pilote ou exécute les cards via `task_list` et `task_update`, sans
  dépendre d'un fichier `PLAN.md` ;
- les cards marquées parallélisables ne sont pas parallélisées par le simple
  statut `queued` : `/dev` doit les déléguer à `spawn_agent`, un worker par
  task indépendante, puis clôturer chaque card selon le rapport reçu ;
- le scheduler Kanban reste un consommateur séquentiel de tasks `queued` pour un
  agent donné ; il ne porte pas la logique métier de parallélisation ;
- `PLAN.md` reste seulement une entrée legacy ou explicitement demandée par
  l'utilisateur, jamais le protocole natif ;
- les branches restent liées aux tasks et le merge final appartient à
  l'utilisateur, sauf demande explicite contraire.

## 2026-05-15 — Exécution des routines via canal dédié

Le bouton de test du dashboard et le cron des routines doivent utiliser le même
chemin d'exécution `channel=routine`.

Conséquences :
- le dashboard ne simule pas un message web utilisateur pour tester une routine ;
- le client cron/dashboard garde la connexion gateway ouverte jusqu'au `done`
  du tour, sinon le gateway considère le client parti et annule le tour ;
- les demandes de permission émises pendant une routine sont refusées par défaut
  côté exécuteur non interactif.

## 2026-05-15 — Overrides d'identité par agent

`SOUL.md`, `IDENTITY.md` et `USER.md` ont une version globale sous `~/.marius`,
mais un agent peut les surcharger dans son workspace `~/.marius/workspace/<agent>/`.

Conséquences :
- au runtime, le fichier agent est utilisé s'il existe ; sinon le fichier global
  correspondant sert de fallback ;
- l'existence d'un fichier agent vide masque aussi le global, ce qui permet un
  bypass explicite ;
- lors de la création d'un nouvel agent, les documents globaux existants sont
  copiés dans son workspace sans écraser d'éventuels overrides ;
- le dashboard, lorsqu'il édite depuis un panneau agent, édite uniquement le
  fichier agent et affiche un document vide si aucun override n'existe encore.

## 2026-05-15 — Frontière Task Board / Routines / Chat

Le Task Board est la vue des tâches uniques suivies explicitement. Les routines
sont des définitions récurrentes séparées ; leurs runs ne créent pas de clone
dans le Task Board.

Conséquences :
- une task visible dans le Task Board a `recurring=false` ;
- une routine visible dans `Routines.cron` a `recurring=true` ;
- un run de routine réutilise l'objet routine, met à jour ses événements /
  `last_run` / `last_error`, et publie seulement la réponse assistant ;
- une task unique programmée (`scheduled_for`) reste le même objet du Task Board
  et passe par le même prompt interne `[Task Board]` qu'un lancement manuel ;
- les prompts internes `routine` et `task` ne sont pas ajoutés comme messages
  utilisateur visibles dans la conversation canonique ;
- une demande de chat immédiate ne crée pas de task sauf si l'utilisateur demande
  explicitement un suivi, un backlog, une planification ou une routine.
- une task créée depuis un agent hérite de cet agent par défaut si le champ
  `agent` est omis ; le modèle peut seulement surcharger explicitement quand
  l'utilisateur demande un autre agent.
- une task unique qui porte un `project_path` explicite autorise ce chemin comme
  racine du run avant d'envoyer le prompt au gateway, sous contrôle du guardian
  policy ; cela permet de créer un nouveau projet demandé sans ask non interactif
  bloquant.
- les statuts canoniques des tasks sont `backlog`, `queued`, `running`, `done`,
  `failed` et `paused` ; `archived` n'est plus un statut de task et les anciennes
  valeurs sont relues comme `done`.
- `paused` reste visible dans le Kanban, dans la colonne `BACKLOG`, avec un badge
  explicite.
- en mode `limited`, la création/activation d'un nouveau dossier projet frère
  d'une racine déjà autorisée est permise pour `make_dir` et `project_set_active`,
  mais pas pour des écritures arbitraires avant que ce projet devienne une racine
  autorisée.
- les demandes de permission émises par une task ne sont pas auto-refusées par
  le scheduler : elles sont relayées aux clients ouverts pour permettre un ask
  utilisateur normal, puis la task reprend avec la réponse.
- une task unique `backlog` est inerte ; une task unique `queued` est consommée
  par le scheduler, immédiatement si elle n'a pas de `scheduled_for`, à l'heure
  prévue sinon. Le dashboard ne doit donc pas exposer de bouton "launch" pour les
  tasks uniques : il permet seulement de cadrer, mettre en queue ou retry.
- après un run scheduler terminé, une task unique passe `done` automatiquement
  si l'agent n'a pas explicitement posé un autre statut via `task_update` ;
- déplacer manuellement une task unique `running` vers `backlog` annule le run
  en cours : le lock est nettoyé, le runner ferme sa connexion au gateway, et
  la fin tardive du scheduler ne doit pas remettre la task en `done` ou `failed` ;
- au redémarrage d'un gateway, une task unique restée `running` passe `failed`
  au lieu d'être rejouée automatiquement. Le retry d'une task unique interrompue
  doit être explicite.

## 2026-05-15 — Taxonomie des outils côté backend

Le runtime/config backend est la source de vérité des outils disponibles et de
leur regroupement UX.

Conséquences :
- `/api/tools` expose la liste des outils, les outils admin-only, les outils
  toujours inclus et les groupes d'affichage ;
- le dashboard affiche ces groupes sans maintenir sa propre taxonomie produit ;
- les skills restent découverts dynamiquement par `/api/skills` ;

## 2026-05-15 — Outils requis par skills actifs

Un skill peut dépendre d'outils runtime natifs. Dans ce cas, l'activation du
skill doit rendre ces outils accessibles à l'agent, même si une ancienne config
d'agent avait une liste d'outils explicite antérieure.

Conséquences :
- le skill `kanban` active automatiquement `task_create`, `task_list` et
  `task_update` ;
- les outils requis par skill restent filtrés par les règles de rôle/admin ;
- le dashboard et le gateway passent par la même résolution effective, afin que
  l'UI et le runtime ne divergent pas.

## 2026-05-15 — Catalogue d'outils piloté par la factory

La liste des outils exposés par la config et le dashboard ne doit pas être une
copie manuelle du registre runtime.

Conséquences :
- `ALL_TOOLS` est dérivé du catalogue de `marius.tools.factory` ;
- les groupes UX classent cette liste et mettent les outils inconnus en
  fallback `Other` ;
- la config ne persiste pas une allowlist `tools` ni un `tools_mode` : elle
  persiste seulement `disabled_tools` ;
- les outils actifs sont toujours résolus comme catalogue courant autorisé par
  rôle, moins `disabled_tools`, plus les outils requis par skills actifs ;
- les outils liés au runtime (`reminders`, `spawn_agent`, `call_agent`) sont
  catalogués et construits par la même factory que les autres outils ; leur
  instanciation peut dépendre du contexte courant, mais pas leur exposition UX ;
- un nouvel outil du registre est donc visible et actif par défaut, sauf si
  l'agent désactive explicitement son groupe ou cet outil ;
- un outil nouveau non classé explicitement tombe dans un groupe `Other` afin
  d'éviter qu'il existe côté runtime sans être visible dans l'éditeur d'agent.

## 2026-05-15 — Routage vision native / vision locale

Une image jointe par l'utilisateur est un artefact du tour, pas seulement un
texte contenant un chemin de fichier.

Conséquences :
- si l'outil `vision` est actif pour l'agent, l'image reste traitée comme un
  fichier joint local et le modèle peut appeler l'outil `vision` Ollama ;
- si l'outil `vision` est désactivé, le gateway tente la vision native du
  modèle courant en transmettant l'image attachée à l'adapter provider ;
- seuls les fichiers image réellement uploadés dans le workspace de l'agent sont
  convertis en artefacts natifs, afin d'éviter qu'un prompt texte force l'envoi
  arbitraire d'un fichier local à un provider cloud ;
- si le provider/modèle ne supporte pas l'image native, l'erreur provider reste
  visible et l'utilisateur peut activer l'outil `vision` local.

## 2026-05-15 — Contrôle navigateur comme skill

Le contrôle navigateur Playwright est une capacité agentique complète, pas un
outil global activé par défaut.

Conséquences :
- les outils `browser_*` existent dans le catalogue runtime et le dashboard,
  mais sont des outils gated par le skill `browser` ;
- un agent sans le skill `browser` ne reçoit pas ces outils, même si sa config
  ancienne avait une liste d'outils large ;
- activer le skill `browser` rend disponibles `browser_open`,
  `browser_extract`, `browser_screenshot`, `browser_click`, `browser_type` et
  `browser_close` ;
- les actions de lecture/navigation sont autorisées comme capacités web, tandis
  que les interactions (`click`, `type`) passent par le gardien en modes non
  `power` ;
- l'implémentation Playwright reste optionnelle : si la dépendance ou Chromium
  manque, l'outil retourne une erreur explicite au lieu de casser le runtime.

## 2026-05-15 — Projet actif lors du cadrage de task

Une action explicite sur une task projetée doit travailler dans le projet de la
task.

Conséquences :
- le bouton `Plan` du Task Board active le `project_path` de la task avant
  d'ouvrir le draft de cadrage dans le chat ;
- si la task n'a pas encore de `project_path` mais que la vue Task Board est
  filtrée sur un projet, ce projet est écrit sur la task puis activé ;
- activer un projet depuis le dashboard peut enregistrer au passage un dossier
  existant non encore présent dans `projects.json` ;
- le system prompt rappelle le projet actif explicite et demande de basculer
  via `project_set_active` seulement quand l'utilisateur veut réellement
  travailler sur ce projet, pas lorsqu'il le cite comme référence.

## 2026-05-14 — Zone de confiance runtime en mode limited

En mode `limited`, la zone de confiance effective d'un gateway est composée du
workspace interne de l'agent et des roots explicitement validées par le gardien.
Le projet actif est une root candidate : il n'est ajouté à l'allow-list
persistante qu'après décision `allow` de `guardian_policy`.

Conséquences :
- les lectures/écritures de base sous le projet actif ne déclenchent pas une
  demande d'autorisation à chaque fichier une fois la root validée ;
- le projet actif est relu au moment de la vérification, mais il passe par le
  détecteur de projet et la politique d'expansion avant d'être trusted ;
- les roots validées sont persistées dans `~/.marius/allowed_roots.json` ;
- le mode `safe` reste plus strict et ne promeut pas le projet actif en zone
  d'écriture libre ;
- les dossiers trop larges comme `~`, les chemins système ou les grands dossiers
  utilisateur (`~/Documents`, `~/Downloads`, etc.) ne sont pas promus ;
- les chemins système et fichiers sensibles restent filtrés par le gardien.

## 2026-05-14 — Création de projet depuis le Task Board

Le Task Board peut marquer une tâche avec `project_path: "nouveau"` pour
signaler qu'elle crée un nouveau projet plutôt qu'elle ne travaille dans un
projet existant.

Au lancement, le dashboard résout le nom/chemin du projet depuis le titre ou le
prompt, limite la création à `~/Documents/projets`, crée le dossier, l'ajoute
aux projets connus et l'ajoute à l'allow-list persistante avant d'envoyer la
tâche au gateway.

Conséquences :
- le LLM reçoit une task déjà attachée au vrai chemin projet ;
- la création du dossier et la promotion en zone de confiance ne dépendent pas
  d'une formulation implicite du modèle ;
- un projet créé via le board apparaît ensuite comme projet normal dans le
  filtre du dashboard.

## 2026-05-14 — Activation directe d'un nouveau projet

Le workflow conversationnel/CLI doit pouvoir couvrir "crée un nouveau projet X
dans le dossier de projets" sans dépendre d'une séquence implicite
`make_dir` puis `project_set_active`.

`project_set_active` accepte donc `create=true` :
- le gardien demande l'autorisation d'écrire le nouveau dossier et les fichiers
  de registre Marius ;
- l'outil crée le dossier si nécessaire ;
- il définit ce dossier comme projet actif ;
- il ajoute la root à l'allow-list persistante quand le tool est construit dans
  le runtime Marius.

Ce flux garde le modèle responsable de choisir l'outil, mais rend l'opération
atomique côté système une fois l'autorisation donnée.

## 2026-05-13 — call_agent : délégation vers agents nommés persistants

`call_agent` permet à l'agent orchestrateur (admin) de déléguer une tâche à un
agent nommé persistant via son gateway Unix, et de récupérer sa réponse complète.

**Différence avec `spawn_agent`** :
- `spawn_agent` crée des workers éphémères anonymes à partir de la config du parent.
- `call_agent` route une tâche vers un agent existant et persistant (avec sa propre
  mémoire, ses propres skills, son historique de session).

**Implémentation** :
- Connexion au socket `~/.marius/run/<agent>.sock`.
- Handshake WelcomeEvent → envoi InputEvent → collecte DeltaEvents → DoneEvent.
- Les `permission_request` de l'agent cible sont auto-refusés (pas d'interactivité).
- Timeout configurable (défaut 120s, max 300s).
- Non disponible pour les agents nommés par défaut (`AGENT_DEFAULT_DISABLED_TOOLS`),
  activable explicitement si un agent doit lui-même orchestrer d'autres agents.

## 2026-05-12 — Hiérarchie à trois niveaux : admin, agent, spawned

Trois niveaux d’agent, règles explicites et non négociables.

**Admin** (`role = "admin"`) :
- Créé une seule fois à `marius setup` ; c’est le premier agent configuré.
- Ne peut jamais être supprimé (`host_agent_delete` et dashboard le refusent).
- Peut créer des agents nommés et spawner des subagents à runtime.
- Dispose d’un gateway complet : CLI, web, Telegram, scheduler.

**Agent nommé** (`role = "agent"`) :
- Créé par l’admin via config (`host_agent_save` ou dashboard).
- Peut être supprimé par l’admin.
- Dispose de son propre gateway : CLI, web, Telegram, scheduler.
- Ne spawne pas de subagents par défaut — `spawn_agent` n’est pas dans son toolset initial.
- Peut recevoir explicitement `spawn_agent` si l’usage devient pertinent pour cet agent.
- Ne reçoit pas les outils de mutation host/admin globale par défaut ; la création,
  suppression, configuration Telegram, providers/secrets sensibles et apply/rollback
  self-update restent du côté admin.

**Subagent spawné** (éphémère, pas dans `config.json`) :
- Créé à runtime par l’admin pour une tâche bornée (développement, délégation).
- Disparaît à la fin de la tâche, aucun état persistant.
- Pas de gateway, pas de Telegram.
- **Ne peut pas spawner d’autres subagents** — depth = 1, déjà appliqué par `spawn_agent` qui filtre lui-même du toolset worker.

Implémentation :
- `AgentConfig` reçoit `role: str = "agent"`.
- À `marius setup`, l’agent initial est créé avec `role = "admin"`.
- Migration transparente : si `role` est absent dans `config.json`, `_from_dict` l’infère à `"admin"` pour `main_agent`, `"agent"` pour les autres.
- `host_agent_delete` et le dashboard bloquent la suppression si `role == "admin"` (ou `name == main_agent` pour compat legacy).
- Les agents nommés n’ont pas `spawn_agent` dans leur toolset par défaut, mais
  l’outil reste activable explicitement dans leur config.
- Le toolset effectif est aussi filtré au runtime par rôle, pour neutraliser les
  anciennes configs ou ajouts manuels qui remettraient un outil admin-only
  global à un agent nommé. `spawn_agent` n’est pas admin-only.

## 2026-05-11 — Sortie de tour rendue en commun
- Décision : ajouter un rendu de fin de tour commun qui agrège réponse assistant, artefacts d'outils et notice de compaction.
- Principe : les outils restent des producteurs d'observations ; ils ne court-circuitent pas la réponse du LLM.
- Portée : CLI, gateway web et Telegram utilisent le même rendu Markdown portable, avec adaptation minimale au streaming.
- Impact : les diffs et rapports retournés par les tools restent visibles cross-canaux sans créer une logique concurrente dans chaque surface.
- Rendu : les `diff` et les `report` avec contenu Markdown sont rendus en détail ; les autres artefacts gardent un fallback portable.

## 2026-05-11 — Restart gateway différé et secrets hors modèle
- Décision : exposer `host_gateway_restart` comme redémarrage planifié, pas comme arrêt immédiat du processus courant.
- Principe : le tool retourne d'abord un `ToolResult`; le modèle peut donc faire son récap avant que le gateway redémarre.
- Décision secret : `secret_ref_prepare_file` crée un fichier local privé `0600` et enregistre seulement sa référence.
- Règle : aucune valeur secrète ne doit être fournie au modèle ; l'utilisateur remplit le fichier hors chat.
- Règle agent principal : `host_agent_delete` refuse de supprimer `main_agent`, qui ancre les comportements par défaut CLI/gateway/web/Telegram/scheduler.

## 2026-05-09 — Logs locaux de diagnostic
- Décision : ajouter un journal local JSONL sous `~/.marius/logs/marius.jsonl`, consultable avec `marius logs`.
- Portée initiale : démarrage REPL/gateway, début/fin de tour, réponse vide, erreurs provider, erreurs inattendues, appels outils et résultats outils.
- Principe : previews courts et métadonnées utiles plutôt que transcription complète, pour diagnostiquer sans transformer les logs en historique conversationnel concurrent.
- Impact : le logging est best-effort et ne doit jamais bloquer l’expérience utilisateur ; la commande CLI sert au debug et aux tests manuels.

## 2026-05-10 — Host diagnostics comme outils read-only
- Décision : exposer les diagnostics host utiles au modèle via `host_status`, `host_doctor` et `host_logs`.
- Portée initiale : lecture de config agents, état gateway/systemd, doctor existant et logs JSONL filtrables.
- Principe : ces outils restent read-only et retournent des `ToolResult` structurés ; ils ne court-circuitent pas la réponse finale du LLM.
- Impact : les actions host sensibles (agents CRUD, Telegram, secrets) restent une tranche séparée avec garde de permissions plus stricte.

## 2026-05-10 — Actions host atomiques et secrets par référence
- Décision : exposer les premières actions host sensibles via `host_agent_list`, `host_agent_save`, `host_agent_delete` et `host_telegram_configure`.
- Portée initiale : création/mise à jour/suppression d'agents configurés, changement d'agent principal, configuration Telegram.
- Principe : les écritures passent par le gardien de permissions ; les suppressions demandent `confirm: true`.
- Règle secret : aucun token brut ne doit transiter par les arguments de l'outil ; Telegram accepte seulement `token_ref` (`env:NOM` ou `file:/chemin/token`).
- Impact : la capture de secrets générique et la configuration provider restent une tranche distincte.

## 2026-05-10 — Self-update proposal-only
- Décision : exposer le self-update initial comme outils de proposition, pas d'application.
- Portée initiale : `self_update_propose`, `self_update_report_bug`, `self_update_list`, `self_update_show`.
- Principe : les propositions et bugs sont persistés en Markdown sous `~/.marius/self_updates/`; un diff peut être joint comme artefact portable.
- Règle : un outil self-update ne modifie jamais le code de Marius et refuse les arguments `apply` / `auto_apply`.
- Impact : l'application explicite, le rollback et les rapports post-apply restent une tranche séparée.

## 2026-05-11 — Self-update apply/rollback explicites
- Décision : exposer `self_update_apply` et `self_update_rollback` comme actions sensibles séparées des propositions.
- Règle : `self_update_apply` exige une proposition existante, un patch attaché, `confirm: true`, un dépôt git valide et un worktree propre sauf `allow_dirty` explicite.
- Tests : seules des commandes bornées (`pytest`, `python -m pytest`, `git diff --check`) sont exécutées par l'outil.
- Rollback : `self_update_rollback` inverse uniquement un patch déjà enregistré dans un rapport d'application.
- Principe : aucun agent ne valide seul une update ; le gardien de permissions et la confirmation humaine restent la frontière.

## 2026-05-16 — Retrait du module watch persistant
- Décision : Marius ne garde plus de module `watch_*` ni de skill `watch` dédié.
- Principe : une veille ponctuelle reste une conversation normale avec `web_search`
  quand l'utilisateur la demande ; les routines peuvent appeler les outils
  existants, mais il n'y a plus de topics persistants `~/.marius/watch/`.
- Impact : les anciens choix de veille persistante/automatisée ne sont plus une
  capacité produit active.

## 2026-05-11 — Commandes slash gateway alignées
- Décision : les commandes slash de base (`/help`, `/remember`, `/memories`, `/forget`, `/doctor`, `/dream`, `/context`, `/compact`) sont gérées par le gateway, pas seulement par le REPL local.
- Principe : une commande déclarée dans une surface doit être exécutable de bout en bout sur les surfaces qui l'affichent.
- Règle : les commandes directes retournent du Markdown visible ; les commandes de skill restent résolues en prompt et passent par le LLM.
- Impact : web, Telegram et client gateway partagent le même comportement pour ces commandes, au lieu de laisser le modèle répondre "commande inconnue".

## 2026-05-11 — SearxNG démarré avec Marius
- Décision : quand `web_search` est actif, le REPL local et le gateway tentent de démarrer le SearxNG local fourni par `docker-compose.searxng.yml`.
- Principe : `web_search` doit être utilisable dès le premier tour après lancement, sans demander au modèle de diagnostiquer le backend.
- Portée : démarrage best-effort, attente courte, logs `searxng_startup`; Marius ne plante pas si Docker est absent.
- Désactivation : `MARIUS_SEARCH_AUTO_START=0` coupe cet auto-start ; `MARIUS_SEARCH_URL` personnalisé reste à la charge de l'utilisateur.

## 2026-05-11 — Observations d'outils structurées pour le provider
- Décision : les messages `tool` réinjectés au provider contiennent une observation bornée avec `summary`, `data` et artefacts utiles, au lieu du seul résumé visible.
- Principe : le résumé court reste adapté aux traces UI, mais le modèle doit recevoir la charge utile structurée pour produire sa réponse finale.
- Sécurité : les clés évidentes de secrets (`token`, `api_key`, `password`, etc.) sont masquées avant injection.
- Impact : `web_search` fournit bien ses URLs et snippets au modèle, sans court-circuiter le chat ni transformer l'outil en réponse finale.

## 2026-05-11 — Historique web des conversations visibles
- Décision : archiver les conversations visibles du web au moment de `/new`, sous forme de snapshots JSON par agent.
- Principe : l'historique web est consultable depuis l'interface, mais ne devient pas une source de vérité concurrente du runtime agent.
- Règle : consulter une archive ne réactive pas une ancienne session ; la conversation courante reste portée par le gateway.
- Impact : le web conserve la fluidité multi-canal tout en permettant de retrouver les conversations canoniques clôturées.

## 2026-05-15 — Session visible canonique par agent
- Décision : par défaut, web, CLI gateway, Telegram et routines alimentent la même conversation visible canonique de l'agent courant.
- Principe : le `SessionRuntime` du gateway reste la source de continuité LLM ; `~/.marius/workspace/<agent>/web_history.json` est la projection visible canonique partagée par les surfaces.
- Règle : une surface explicitement ouverte sur une archive ou une session secondaire ne devient pas canonique ; elle ne réactive pas le runtime courant.
- Impact : Telegram et le CLI ne divergent plus silencieusement du web ; `/new` depuis une surface canonique archive puis réinitialise la conversation visible et le runtime.

## 2026-05-15 — Frontière persistante de compaction
- Décision : `/compact` compacte uniquement le contexte runtime court ; il ne supprime pas l'historique visible.
- Principe : le gateway écrit une entrée interne `metadata.kind = "compaction_boundary"` dans `web_history.json`.
- Règle : les surfaces de chat masquent cette entrée, les archives visibles l'ignorent, et la restauration runtime ne réhydrate que les tours postérieurs à la dernière frontière.
- Impact : une compaction reste effective après redémarrage sans casser la lisibilité de la conversation canonique.

## 2026-05-11 — Artefacts observationnels non imprimés par défaut
- Décision : les outils de collecte de contexte comme `rag_search` peuvent retourner des rapports structurés masqués au rendu final.
- Principe : le modèle reçoit les données d'outil et doit produire une synthèse lisible ; le chat ne doit pas recevoir un dump brut après la réponse.
- Règle : les artefacts d'action utiles comme les diffs restent visibles ; les rapports de sources servent d'observations sauf demande explicite.
- Impact : les réponses RAG gagnent en lisibilité sans perdre les données nécessaires au LLM.

## 2026-05-11 — Briefings récurrents par routines
- Décision : les briefings récurrents sont de simples routines avec un `prompt` explicite, pas un mécanisme dédié.
- Principe : les sources RAG, calendrier et dreaming servent à croiser, déduire et prioriser quand la routine le demande ; elles ne doivent pas être imprimées telles quelles.
- Impact : l'utilisateur garde la main sur le coût et le bruit des routines de briefing, sans bloquer les ajouts volontaires.

## 2026-05-11 — Briefings sans moteur dédié
- Décision : il n'y a pas de commande ni d'outil dédié au briefing quotidien ; une routine ordinaire porte le prompt, la cadence et l'agent.
- Principe : optimiser un briefing revient à optimiser la routine correspondante, pas à ajouter un second chemin runtime.
- Impact : les tâches récurrentes restent optimisables en coût/latence sans casser l'expérience du chat principal.

## 2026-05-11 — Migration des skills utilisateur Maurice
- Décision : porter `caldav_calendar` et `sentinelle` comme skills Marius Markdown-first, avec outils Marius natifs lorsque l'ancien skill avait du code.
- Principe : ne pas importer aveuglément les wrappers `tools.py` Maurice ; chaque capacité devient une brique testable sous `marius/tools/`.
- Stockage : `sentinelle` écrit dans le workspace de l'agent courant ; `caldav_calendar` reste une façade locale autour de `vdirsyncer` et `khal`.
- Impact : les skills restent activables par agent, le LLM garde la réponse finale, et les outils ne court-circuitent pas la conversation.

## 2026-05-11 — RAG Markdown comme sources consultables
- Décision : introduire un skill `rag` pour gérer des sources Markdown indexées, distinctes de la mémoire durable.
- Principe : les sources RAG sont consultées au besoin via outils ; `memory.db` reste le coeur des faits utiles au quotidien.
- Format v1 : dossiers/fichiers Markdown façon Obsidian, frontmatter optionnel et tags inline `[always]`, `[important]`, `[routine]`, `[fresh]`, `[archive]`.
- Règle : `[always]` et `[important]` signalent des candidates à injection/promotion, mais l'agent doit décider ou demander validation ; aucun corpus n'est injecté en bloc.
- Indexation : `rag_source_sync` catalogue tous les documents, mais n'indexe le contenu détaillé que pour les chunks taggés `[always]`, `[important]`, `[routine]` ou `[fresh]`; les documents non taggés restent localisables par titre/chemin/inventaire.
- Listes : `rag_checklist_add` remplace l'ancien usage de `todos` pour les ajouts simples en écrivant des entrées Markdown `- [ ] ...` dans une source ou liste RAG.
- Impact : l'ancien skill `todos` est retiré ; les listes/notes Markdown deviennent des sources RAG.

## 2026-05-10 — Projet actif explicite
- Décision : ajouter un pointeur de projet actif explicite sous `~/.marius/active_project.json`, séparé du registre historique `~/.marius/projects.json`.
- Principe : `projects.json` reste un registre de projets connus ; le projet actif est un choix explicite, modifiable via `project_set_active`, et consultable via `project_list`.
- Impact : les commandes de skill projet peuvent s'appuyer sur des outils génériques sans créer une base de tâches concurrente ni deviner agressivement le contexte.

## 2026-05-10 — Approvals et secrets par référence
- Décision : persister un audit des demandes de permissions sous `~/.marius/approvals.json` et les références de secrets sous `~/.marius/secret_refs.json`.
- Principe : le garde de permissions peut consulter une décision mémorisée, mais continue à demander confirmation pour les actions sensibles non connues.
- Règle secret : Marius stocke des références (`env:`, `file:`, `secret:`), jamais des valeurs brutes passées par le modèle.
- Impact : les tools `approval_*` et `secret_ref_*` deviennent des briques administrables, sans court-circuiter la réponse finale du LLM.

## 2026-05-11 — Provider config depuis l'agent
- Décision : exposer la configuration provider via `provider_list`, `provider_save`, `provider_delete` et `provider_models`.
- Principe : ces tools écrivent la source existante `~/.marius/marius_providers.json`; ils ne créent pas un store concurrent.
- Règle secret : `provider_save` refuse les clés brutes et accepte seulement `api_key_ref` (`env:`, `file:` ou `secret:`). Les anciennes clés brutes restent compatibles mais sont masquées dans les sorties.
- Impact : l'agent peut gérer les providers courants sans casser la fluidité du chat ni exposer de secret au modèle.

## 2026-05-11 — Dreaming exposé comme ToolEntry
- Décision : exposer le moteur mémoire via `dreaming_run`, construit dynamiquement par session avec provider, mémoire, skills et projet courant.
- Principe : les tools retournent des `ToolResult` et artefacts Markdown ; le modèle garde la reformulation finale.
- Impact : `/dream`, le scheduler et les appels modèle s'appuient sur le même wrapper, sans dupliquer le moteur `marius.dreaming.engine`.

## 2026-05-09 — Observations courtes de session
- Décision : ajouter une couche d’observations de session non persistante, dérivée des résultats d’outils vérifiés.
- Portée initiale : chemins listés, fichiers lus/écrits, chemins invalides et candidats proposés après `file_not_found` / `dir_not_found`.
- Pourquoi : l’agent doit apprendre pendant la session sans transformer chaque correction temporaire en mémoire durable.
- Impact : ces observations sont injectées dans le prompt système des tours suivants sous `<session_observations>` ; elles restent bornées, dédupliquées, et disparaissent à la fermeture de session.
- Règle : les observations guident le LLM mais ne remplacent pas son orchestration ; les outils ne produisent toujours pas de réponse finale à sa place.

## 2026-05-09 — Postures agent
- Décision : les règles de travail propres à un agent vivent dans `~/.marius/agents/<agent>/postures/`.
- Portée initiale : `postures/dev.md`, chargé seulement quand le contexte dev est actif.
- Pourquoi : ces règles dépendent de l’agent configuré plus que du profil utilisateur global, et ne sont pas des capacités activables comme les skills.
- Impact : sans skill `assistant`, `postures/dev.md` est chargé dès le démarrage local ; avec `assistant`, il est chargé après le trigger de posture dev.
- Règle : la posture système garde les invariants minimaux, puis la posture agent précise/surcharge les habitudes de travail.

## 2026-05-09 — Skill système assistant conditionnel
- Décision : `assistant` devient un skill système reconnu par la configuration, même avant le bloc gateway/workspace complet.
- Portée initiale : quand `assistant` est actif, le contexte charge `IDENTITY.md`, `USER.md` et le skill `onboarding` si ces fichiers manquent. Quand `assistant` est absent, l’onboarding n’est pas injecté automatiquement.
- Pourquoi : l’identité humaine durable et l’onboarding appartiennent au bloc assistant, pas au socle local minimal.
- Impact : `marius skills activate assistant` active ce comportement ; le wizard d’agent affiche `assistant` dans les skills disponibles.
- Règle de posture : sans `assistant`, l’agent est orienté dev local, concis et opérationnel ; il évite l’onboarding, le profil durable et les échanges personnels non demandés.
- En mode `assistant`, la posture démarre normale puis bascule en dev projet dès qu’un outil filesystem/shell touche le projet courant ; la bascule vaut pour les tours suivants.

## 2026-05-08 — Vision comme outil système local
- Décision : la vision est exposée comme un `ToolEntry` système (`vision`) et non comme un provider conversationnel concurrent.
- Implémentation initiale : lecture d’une image locale autorisée par le gardien, appel Ollama local `/api/chat`, modèle `gemma4` par défaut, surcharge possible via `MARIUS_VISION_MODEL` et `MARIUS_VISION_OLLAMA_URL`.
- Pourquoi : le LLM principal garde l’orchestration et reformule la réponse finale ; l’outil ne fournit qu’une observation visuelle exploitable.
- Impact : `vision` suit la politique de lecture fichier (`read_file`) pour les permissions et reste une brique standalone sous `marius/tools/`. Les anciennes configs qui portaient exactement les outils par défaut pré-vision sont migrées vers le nouveau défaut, sans modifier les listes personnalisées.

## 2026-05-08 — Suppression du mode local/global — capacités progressives
- Décision : pas de distinction local/global. Marius a un seul mode ; les fonctionnalités avancées s'activent via des skills.
- Règle : `marius` se lance toujours dans le répertoire courant. La mémoire (project_store + memory.db) est active dans tous les cas.
- Ce qui appartient au skill `assistant` (et non à la config de base) : workspace, USER.md, agents nommés multiples, gateway constant, dreaming planifié.
- Pourquoi : workspace + gateway + dreaming sont interdépendants — ils forment un bloc cohérent qui n'a de sens que si l'agent tourne en permanence. Les packager comme skill est plus propre que de les cacher derrière un mode.
- Impact : `MariusConfig` n'a plus de champ `mode` ni `workspace`. Le wizard `marius setup` ne pose plus la question local/global. USER.md n'est pas créé à l'install de base.

## 2026-05-08 — Architecture mémoire : store illimité + injection sélective
- Décision : le store SQLite est illimité en pratique ; l’injection dans le contexte actif est bornée et sélective.
- Principe : `contexte_actif = global + project[cwd]` — snapshot gelé à l’ouverture de session.
- Deux scopes : `global` (profil user, faits cross-projets) et `project` (contexte d’un projet précis, injecté seulement quand ce projet est actif).
- Pourquoi : un projet dormant doit conserver sa mémoire sans polluer les autres sessions ; la sélectivité se fait à l’injection, pas au stockage.
- Impact : `memory_store` reçoit les champs `scope` et `project_path` ; une méthode `get_active_context(cwd)` remplace l’injection par recherche FTS5 par tour.

## 2026-05-08 — Dreaming comme outil agent
- Décision : le dreaming est un `ToolEntry` dans le toolset de l’agent, pas un script externe.
- Trois points d’entrée identiques : appel par l’agent, commande slash utilisateur (`/dream`), cron qui démarre une session isolée et déclenche le tool.
- Pourquoi : interface unifiée, testable, sans logique dupliquée entre CLI et scheduler.
- Impact : le cron ne fait pas de magie — il envoie un message à l’agent qui utilise son tool normalement.

## 2026-05-08 — Dreaming avec LLM obligatoire
- Décision : le dreaming utilise systématiquement un appel LLM pour la consolidation.
- Pourquoi : un dreaming sans LLM consoliderait par fréquence de rappel, ce qui éjecterait les projets dormants mais stratégiques. Seule une couche d’inférence distingue "important mais inactif" de "éphémère et révolu".
- Impact : un appel LLM par dreaming (non par tour) ; le coût est marginal au regard du gain en pertinence sur toutes les sessions futures.

## 2026-05-08 — Skills système avec dream.md
- Décision : chaque skill peut exposer un `dream.md` en plus de son `SKILL.md`.
- `dream.md` : déclare les données que ce skill peut fournir au dreaming.
- Il n'existe pas de skill dédié `dreaming` : le moteur est exposé par l'outil `dreaming_run`, tandis que les skills actifs peuvent contribuer via `DREAM.md`.
- Pourquoi : la logique de contribution au dreaming vit dans les skills Markdown ; le moteur d'agrégation reste une capacité runtime commune.
- Impact : le code ne contient que le pipeline d’agrégation ; le comportement est piloté par les skills.

## 2026-05-08 — Session corpus minimal
- Décision : à la fermeture du REPL (y compris Ctrl-D), écriture automatique d’un fichier session minimal dans `~/.marius/sessions/`.
- Contenu : projet, CWD, timestamps, nombre de tours — pas de résumé LLM.
- Le dreaming lit directement `DECISIONS.md` et `ROADMAP.md` des projets concernés pour le contexte détaillé.
- Pourquoi : éviter de dépendre d’un `/exit` explicite ; garder le fichier session léger (pointeur, pas contenu).
- Impact : les fichiers session sont archivés après traitement par le dreaming, jamais injectés dans le contexte actif.

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

## 2026-05-08 — Host router minimal
- Décision : garder le host comme une surface mince qui transforme une requête entrante en `TurnInput`, délègue au `runtime_orchestrator` puis renvoie un `OutboundPayload` visible.
- Contrat minimal :
  - `InboundRequest` porte le canal, la session, le peer, le texte et des métadonnées ;
  - `HostRouter` gère un registre de sessions léger et un `ui_history_store` visible en mémoire ;
  - la réponse visible provient du `render_adapter` quand le provider renvoie un assistant, sinon d’un fallback stable.
- Pourquoi : matérialiser la frontière host sans y réintroduire le cœur du produit ni mélanger transport, session et rendu.
- Impact :
  - le host ne possède pas la logique provider ;
  - l’historique visible reste séparé du contexte interne du kernel ;
  - cette brique peut servir plus tard de base à CLI/web/Telegram sans changer le noyau.
