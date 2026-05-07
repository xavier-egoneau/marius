# Plan — Définir le périmètre du kernel de Marius

## Goal
Clarifier précisément ce que le **kernel** de Marius doit comprendre, ce qui doit rester dans le **host / channel layer / UI**, et comment traduire cette frontière en briques modulaires cohérentes avec `DECISIONS.md`, `ROADMAP.md` et `BRICKS.md`.

## Current context / assumptions
- Projet actif : `/home/egza/Documents/projets/marius`
- Le projet vise une réécriture de Maurice en version plus modulaire, plus lisible et plus réutilisable.
- Les décisions existantes imposent :
  - LLM au centre
  - guard de sécurité séparé
  - contexte déclaré en Markdown
  - canaux CLI / web / Telegram
  - compaction qui ne supprime pas l’historique visible utilisateur
  - rendu Markdown cohérent cross-canaux
  - diffs exposables dans le workflow dev/self-update
- Les documents présents sont encore surtout d’architecture et de cadrage, pas d’implémentation détaillée.

## Desired outcome
Produire une définition stable du kernel qui permette ensuite de découper le code sans ambiguïté et d’éviter que le kernel absorbe par erreur des responsabilités de surface, d’UI ou de canal.

## Proposed approach
Partir d’une règle simple :

> Le **kernel** contient les règles universelles d’exécution agentique.
> Le **host** contient l’adaptation aux surfaces, au runtime et aux canaux.
> L’**UI** contient le rendu visible et l’expérience utilisateur.
> Le **storage** contient la persistance spécialisée (sessions, mémoire, artefacts, index, journaux).

Ensuite dériver une cartographie explicite des responsabilités, contrats et flux.

## Step-by-step plan

### 1. Formuler le contrat conceptuel du kernel
Définir dans un document d’architecture une phrase de référence du type :
- le kernel orchestre une requête agentique indépendamment du canal d’entrée ;
- il ne connaît ni Telegram, ni le web, ni la CLI comme surfaces concrètes ;
- il expose des contrats stables à destination du host.

### 2. Lister les responsabilités autorisées du kernel
Le kernel doit comprendre :
- les types / contrats centraux : messages, événements, décisions, appels d’outils, résultats d’outils, approvals, erreurs ;
- le pipeline logique d’un tour :
  - réception d’une requête normalisée,
  - construction du contexte logique,
  - décision d’appel provider,
  - exécution / arbitrage d’outils,
  - synthèse de sortie structurée ;
- les politiques de session courte :
  - continuité conversationnelle,
  - compaction interne,
  - estimation de fenêtre de contexte,
  - seuils de trim / summarize / reset ;
- l’interface du guard de sécurité et les décisions de permission ;
- l’interface des providers et la normalisation streaming / erreurs ;
- les contrats de skills et d’outils au niveau abstrait ;
- les mécanismes nécessaires à la cohérence cross-canaux au niveau **sémantique** :
  - métadonnées de message,
  - artefacts de type diff,
  - notices de compaction,
  - distinction entre historique interne et historique visible.

### 3. Lister explicitement ce qui est hors kernel
Le kernel ne doit pas comprendre :
- les API Telegram / HTTP / TUI / web ;
- le rendu Markdown spécifique à un canal ;
- la présentation UI des diffs, boutons, panels, statuts, notifications ;
- la gestion des routes HTTP, websockets, polling Telegram, commandes slash ;
- la sélection d’un projet via une interaction UI ;
- les conventions de stockage spécifiques à une surface ;
- les détails de persistance “historique visible utilisateur” si ce stockage est orienté produit/UI plutôt que logique de session.

### 4. Découper les frontières kernel / host / UI / storage
Proposer une matrice de responsabilité :

#### Kernel
- `contracts`
- `session_logic`
- `compaction_logic`
- `provider_protocol`
- `permission_protocol`
- `tool_call_protocol`
- `context_assembly_rules`

#### Host
- `channel_adapters` (CLI, web, Telegram)
- `request_normalization`
- `session_binding`
- `project selection / active context binding`
- `notification routing`
- `attachment ingestion`

#### UI
- rendu Markdown / HTML / chat
- blocs diff visibles
- notices de compaction affichées
- regroupement des activités outils
- affordances de review / validation

#### Storage
- session store
- ui history store
- memory store
- artifact store
- proposal / diff store
- indexes de recherche

### 5. Définir la place de la compaction
Clarifier noir sur blanc :
- le kernel peut compacter le **contexte de travail** ;
- le kernel ne doit pas décider seul d’effacer l’**historique visible utilisateur** ;
- si un résumé remplace une portion du contexte interne, il faut conserver des métadonnées permettant au host / storage / UI de garder la continuité visible ;
- les notices de compaction sont un objet de domaine stable, mais leur affichage précis appartient à l’UI.

### 6. Définir la place du Markdown cross-canaux
Séparer deux niveaux :
- **niveau kernel** : production d’un contenu structuré compatible avec le rendu Markdown, plus métadonnées/artefacts ;
- **niveau host/UI** : adaptation du rendu aux contraintes du canal (Telegram, web, CLI), échappement, tronquage, blocs spéciaux, pièces jointes natives.

Décision cible : le kernel ne “parle” pas Telegram ou HTML ; il produit des sorties suffisamment structurées pour être rendues proprement partout.

### 7. Définir la place des diffs dans le système
Formaliser que les diffs sont :
- des **artefacts de domaine** reconnus par le kernel ou par un contrat partagé ;
- pas seulement du texte brut ;
- attachables à des tours / tool results ;
- rendables différemment selon surface ;
- persistables et réinjectables dans l’historique visible.

### 8. Traduire la théorie dans `BRICKS.md`
Mettre à jour ou compléter `BRICKS.md` avec au moins les briques suivantes si elles ne sont pas déjà assez nettes :
- `kernel_contracts`
- `session_runtime`
- `compaction_engine`
- `provider_adapter`
- `security_guard`
- `tool_router`
- `channel_host`
- `render_adapter`
- `artifact_store`
- `ui_history_store`

But : rendre explicite ce qui est réutilisable hors Marius et ce qui ne l’est pas.

### 9. Traduire la théorie dans `DECISIONS.md`
Ajouter ou reformuler des décisions durables sur :
- la frontière kernel / host ;
- la différence entre historique interne et historique visible ;
- le statut des diffs comme artefacts ;
- le rôle du Markdown comme format logique portable plutôt que rendu final unique.

### 10. Préparer le futur squelette de code
Quand l’architecture sera validée, créer un squelette de packages ressemblant à :
- `marius/kernel/`
- `marius/host/`
- `marius/render/`
- `marius/storage/`
- `marius/contracts/` ou contrats dans `kernel/contracts.py`

Sans implémenter trop tôt, juste assez pour verrouiller les frontières.

## Files likely to change
- `DECISIONS.md`
- `ROADMAP.md`
- `BRICKS.md`
- futur document d’architecture détaillé, par exemple :
  - `ARCHITECTURE.md`
  - ou `docs/architecture/kernel-boundaries.md`
- plus tard, futurs modules de code :
  - `marius/kernel/*`
  - `marius/host/*`
  - `marius/render/*`
  - `marius/storage/*`

## Validation / tests
### Validation architecture
- Vérifier qu’on peut répondre sans ambiguïté à :
  - « est-ce que Telegram appartient au kernel ? » → non
  - « est-ce que la compaction appartient au kernel ? » → oui, pour le contexte interne
  - « est-ce que l’historique visible appartient au kernel ? » → seulement via contrat/logique minimale, pas via rendu produit
  - « est-ce qu’un diff est un simple texte ? » → non, c’est un artefact structuré

### Validation de conception
- Pour chaque future classe/module, demander :
  - dépend-elle d’un canal concret ?
  - manipule-t-elle de l’UI ?
  - manipule-t-elle des règles universelles ?
  - pourrait-on la réutiliser dans un autre assistant ?

### Validation future du code
Quand le code existera, viser :
- tests unitaires du moteur de compaction ;
- tests unitaires des contrats provider / tool / permission ;
- tests d’intégration host ↔ kernel ;
- tests de rendu cross-canaux pour vérifier Markdown/diff/notices.

## Risks / tradeoffs
- **Risque de kernel trop gros** : si on y met les détails de canal, on recrée un monolithe.
- **Risque de kernel trop maigre** : si tout fuit vers le host, on perd la réutilisabilité.
- **Risque de confusion entre logique et rendu** : surtout autour du Markdown, des diffs et de la compaction.
- **Risque de stockage mal découpé** : l’historique visible et le contexte interne ne doivent pas être confondus.

## Open questions
1. Le `context_builder` vit-il entièrement dans le kernel ou partiellement dans le host selon mode local/global ?
2. Les artefacts (`diff`, `image`, `report`, etc.) doivent-ils être définis dans les contrats kernel ou dans une couche partagée annexe ?
3. Souhaite-t-on un `render_adapter` comme brique standalone distincte, ou l’intégrer au host ?
4. Où placer exactement la logique de “session canonique” : host pur, ou contrat kernel minimal + orchestration host ?

## Recommended next move
Après validation de ce plan, produire un document court de référence du style :
- **Kernel = logique universelle**
- **Host = adaptation runtime/canaux**
- **UI = rendu visible**
- **Storage = persistance spécialisée**

Puis seulement mettre à jour `BRICKS.md` et `DECISIONS.md` de manière cohérente.