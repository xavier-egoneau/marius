# Plan — Marius v2 : plan par brique

## Goal
Reprendre l’ensemble des points clarifiés dans la discussion et en déduire un **plan par brique** pour Marius v2, avec une frontière nette entre :
- **kernel**
- **host / channels**
- **render / UI**
- **storage / persistance**

Le but est d’obtenir un découpage implémentable, réutilisable et cohérent avec les décisions déjà posées :
- LLM au centre
- guard séparé
- contexte en Markdown
- modes local/global
- session canonique globale + branches ciblées
- compaction interne sans perte de l’historique visible utilisateur
- rendu Markdown cohérent cross-canaux
- diffs exposables comme artefacts du workflow dev

---

## Current context / assumptions

### Ce qu’on s’est dit et qu’il faut intégrer
1. **La compaction ne doit pas supprimer l’historique pour l’utilisateur.**
   - Elle peut réduire le **contexte interne**.
   - Elle peut produire des **résumés dérivés**.
   - Mais l’**historique visible** doit rester préservé.

2. **Le système doit estimer la pression de contexte par rapport au modèle.**
   - Fenêtre de contexte estimée / connue.
   - Seuils de trim / summarize / reset.
   - Possibilité d’utiliser une mesure plus fiable si le provider expose les tokens réels.

3. **Le Markdown doit survivre aux canaux.**
   - Une même conversation doit rester lisible entre CLI, web et Telegram.
   - Le kernel ne doit pas connaître le rendu Telegram/HTML concret.
   - Il faut un niveau logique portable + un niveau adaptation/rendu.

4. **Les diffs de dev/self-update sont des objets importants.**
   - Ils ne doivent pas être traités comme simple texte jetable.
   - Ils doivent pouvoir être attachés à un tour, persistés, rendus et relus.

5. **Tout cela n’appartient pas entièrement au kernel.**
   - Le kernel porte la logique universelle.
   - Le host transporte/adapte.
   - L’UI rend.
   - Le storage conserve les vues et artefacts spécialisés.

### Documents projet déjà présents
- `AGENTS.md`
- `DECISIONS.md`
- `ROADMAP.md`
- `BRICKS.md`

---

## Proposed architecture rule

### Règle simple
> **Kernel = signification universelle**  
> **Host = adaptation runtime / canaux**  
> **Render/UI = présentation visible**  
> **Storage = persistance spécialisée**

### Conséquence pratique
- Le kernel comprend **ce qu’est** un message, une session, une compaction, un diff, une permission.
- Le host comprend **d’où vient** une requête et **où va** une réponse.
- L’UI comprend **comment ça s’affiche**.
- Le storage comprend **comment ça se conserve** sans mélanger contexte interne et historique visible.

---

# Plan par brique

## Brique 1 — `kernel_contracts`

### Rôle
Définir les types, contrats et objets universels du système.

### Ce qu’elle doit comprendre
- `Message`
- `SessionTurn`
- `ToolCall`
- `ToolResult`
- `ProviderRequest` / `ProviderChunk` / `ProviderResponse`
- `PermissionDecision`
- `ApprovalRequest`
- `Artifact`
- `CompactionNotice`
- `ContextUsage`

### Ce qu’elle ne doit pas comprendre
- Telegram / HTTP / WebSocket / TUI
- HTML / rendu Markdown final
- format d’API spécifique à une UI

### Sous-plans
1. Définir la liste canonique des objets de domaine.
2. Définir les champs minimaux stables.
3. Définir la notion d’artefact générique :
   - `diff`
   - `image`
   - `report`
   - `file`
4. Définir une distinction explicite entre :
   - message interne de contexte
   - message visible utilisateur
   - notice système visible
5. Définir les métadonnées nécessaires pour lier un message à :
   - une corrélation de tour
   - un artefact
   - une compaction
   - une activité outil

### Fichiers likely to change
- `BRICKS.md`
- futur `marius/kernel/contracts.py`
- éventuel `docs/architecture/contracts.md`

### Validation
- Un objet de type `diff` peut être reconnu sans connaître la surface.
- Une notice de compaction peut être comprise sans connaître l’UI.
- Les objets peuvent être importés ailleurs.

---

## Brique 2 — `provider_adapter`

### Rôle
Normaliser l’appel aux providers LLM.

### Ce qu’elle doit comprendre
- auth
- génération / streaming
- erreurs provider
- retour de métriques si disponibles
- information de tokens si disponible

### Ce qu’elle ne doit pas comprendre
- logique projet
- session canonique
- rendu final
- choix UI

### Sous-plans
1. Définir l’interface provider minimale : `generate`, `stream`, `capabilities`, `usage`.
2. Définir un contrat de retour d’usage de contexte/tokens.
3. Définir comment remonter :
   - `input_tokens`
   - `output_tokens`
   - fenêtre max connue si disponible
4. Définir les erreurs normalisées.
5. Prévoir un fallback quand le provider ne donne pas d’info fiable.

### Fichiers likely to change
- `BRICKS.md`
- futur `marius/kernel/provider.py` ou `marius/providers/adapter.py`

### Validation
- Le kernel peut demander une génération sans connaître le provider concret.
- Le système peut utiliser des tokens réels si exposés.

---

## Brique 3 — `security_guard`

### Rôle
Arbitrer les actions sensibles avant exécution.

### Ce qu’elle doit comprendre
- intention d’action
- classe de risque
- contexte de permission minimal
- décision : allow / deny / ask

### Ce qu’elle ne doit pas comprendre
- la conversation complète comme UI
- les canaux concrets
- la stratégie de rendu de la demande de confirmation

### Sous-plans
1. Définir les classes d’action sensibles.
2. Définir les décisions du guard.
3. Définir le TTL éventuel des approvals.
4. Définir le protocole entre kernel et guard.
5. Définir la remontée d’une demande de confirmation vers le host.

### Fichiers likely to change
- `BRICKS.md`
- futur `marius/kernel/permissions.py`
- futur `marius/kernel/approvals.py`

### Validation
- Le guard peut être appelé par n’importe quel host.
- Il ne reformule pas la réponse utilisateur à la place du LLM.

---

## Brique 4 — `context_builder`

### Rôle
Assembler le contexte logique envoyé au LLM à partir des documents et signaux utiles.

### Ce qu’elle doit comprendre
- Markdown source de vérité
- contexte projet actif
- décisions durables
- mémoire utile
- signaux de session

### Ce qu’elle ne doit pas comprendre
- rendu final d’un document dans l’UI
- sélection de projet pilotée par interface
- heuristique agressive de navigation entre projets

### Sous-plans
1. Définir les entrées du builder :
   - projet actif
   - mode local/global
   - mémoire générale
   - mémoire projet
   - documents Markdown
2. Définir l’ordre de priorité des sources.
3. Définir ce qui survit à la compaction :
   - décisions
   - repères projet
   - résumés dérivés
4. Définir le format de sortie logique du contexte.
5. Définir les limites pour éviter la sur-injection.

### Fichiers likely to change
- `BRICKS.md`
- futur `marius/kernel/context_builder.py`
- futur doc `docs/architecture/context.md`

### Validation
- Le builder peut produire un contexte sans connaître Telegram ou web.
- Le projet actif reste explicite.

---

## Brique 5 — `project_context`

### Rôle
Porter les règles du projet actif et la séparation entre projet courant et projets cités.

### Ce qu’elle doit comprendre
- projet actif
- références projet
- basculement explicite
- distinction local/global

### Ce qu’elle ne doit pas comprendre
- UI de sélection
- navigation web
- logique provider

### Sous-plans
1. Formaliser le contrat du projet actif.
2. Formaliser le comportement en mode local.
3. Formaliser le comportement en session canonique globale.
4. Formaliser le comportement des branches ciblées.
5. Définir les métadonnées minimales pour rattacher une requête à un projet.

### Fichiers likely to change
- `DECISIONS.md`
- `BRICKS.md`
- futur `marius/kernel/project_context.py`

### Validation
- Un projet cité ne devient pas actif implicitement.
- Une branche ciblée garde son contexte propre.

---

## Brique 6 — `session_runtime`

### Rôle
Gérer l’état conversationnel court et les tours de session.

### Ce qu’elle doit comprendre
- session id
- tour
- corrélation
- contexte court
- activité outil liée à un tour

### Ce qu’elle ne doit pas comprendre
- historique UI complet comme produit
- polling / sockets / API web
- affichage des conversations

### Sous-plans
1. Définir la structure minimale d’une session logique.
2. Définir les liens entre messages d’un même tour.
3. Définir l’attachement des résultats outils à un tour.
4. Définir la gestion des branches vs session canonique.
5. Définir les points d’extension pour compaction et résumés.

### Fichiers likely to change
- `BRICKS.md`
- futur `marius/kernel/session.py`

### Validation
- Une session logique peut vivre indépendamment du canal.
- Un tool result et un diff peuvent être rattachés à un tour.

---

## Brique 7 — `compaction_engine`

### Rôle
Compacter le contexte de travail sans détruire la continuité visible utilisateur.

### Ce qu’elle doit comprendre
- estimation de tokens
- usage remonté par provider
- seuils de compaction
- niveaux de trim/summarize/reset
- résumé interne
- notice de compaction logique

### Ce qu’elle ne doit pas comprendre
- suppression de l’historique visible côté produit
- manière d’afficher la notice à l’écran
- stratégie spécifique Telegram/web

### Sous-plans
1. Définir la structure de `CompactionConfig`.
2. Définir la logique d’estimation des tokens.
3. Définir le fallback entre estimation heuristique et métriques provider.
4. Définir la politique de seuils.
5. Définir les objets produits :
   - contexte compacté
   - résumé dérivé
   - notice logique
6. Définir le contrat avec le storage/UI pour préserver l’historique visible.

### Fichiers likely to change
- `ROADMAP.md`
- `DECISIONS.md`
- `BRICKS.md`
- futur `marius/kernel/compaction.py`

### Validation
- La compaction réduit le contexte interne.
- L’historique visible reste récupérable.
- Le moteur n’a pas besoin de connaître l’UI.

---

## Brique 8 — `tool_router`

### Rôle
Exposer les outils disponibles et normaliser leurs résultats.

### Ce qu’elle doit comprendre
- contrats d’outils
- exécution d’outil
- normalisation du résultat
- attachement d’artefacts

### Ce qu’elle ne doit pas comprendre
- présentation UI finale
- logique Telegram/web
- réécriture conversationnelle finale

### Sous-plans
1. Définir le contrat de tool call.
2. Définir la normalisation de `ToolResult`.
3. Définir comment un outil attache un artefact `diff`.
4. Définir le lien entre résultat outil et session/tour.
5. Définir l’intégration avec le guard.

### Fichiers likely to change
- `BRICKS.md`
- futur `marius/kernel/tools.py`

### Validation
- Un outil peut produire un diff structuré.
- Le résultat peut être rendu ailleurs sans perdre le sens.

---

## Brique 9 — `artifact_store`

### Rôle
Conserver les artefacts persistants liés aux tours, outils et workflows.

### Ce qu’elle doit comprendre
- types d’artefacts
- indexation minimale
- lien session/tour/outil
- stockage des données ou pointeurs

### Ce qu’elle ne doit pas comprendre
- rendu UI des artefacts
- politique conversationnelle
- logique provider

### Sous-plans
1. Définir le modèle de stockage des artefacts.
2. Définir le format minimal du stockage d’un diff.
3. Définir le lien entre artefact et message/tour.
4. Définir la politique de réhydratation dans l’historique visible.
5. Définir une stratégie de taille / truncation sans perdre l’original.

### Fichiers likely to change
- `BRICKS.md`
- futur `marius/storage/artifacts.py`

### Validation
- Un diff long peut être tronqué à l’affichage sans perdre sa version source.
- Un artefact peut être relu après coup.

---

## Brique 10 — `ui_history_store`

### Rôle
Préserver l’historique visible utilisateur indépendamment des compactions internes.

### Ce qu’elle doit comprendre
- messages visibles
- notices visibles
- activité outil visible
- artefacts affichables
- continuité cross-surface

### Ce qu’elle ne doit pas comprendre
- logique de génération provider
- politique de compaction interne
- adaptation fine à chaque canal

### Sous-plans
1. Définir la différence entre :
   - historique logique interne
   - historique visible utilisateur
2. Définir la stratégie append-only de la vue visible.
3. Définir comment réinjecter :
   - notices de compaction
   - tool activity
   - diffs
4. Définir comment éviter la pollution par les messages strictement internes.
5. Définir la compatibilité multi-surfaces.

### Fichiers likely to change
- `DECISIONS.md`
- `BRICKS.md`
- futur `marius/storage/ui_history.py`

### Validation
- Une compaction ne fait pas disparaître la conversation visible.
- Un diff affiché peut être retrouvé.

---

## Brique 11 — `channel_host`

### Rôle
Adapter le système aux canaux concrets : CLI, web, Telegram.

### Ce qu’elle doit comprendre
- origine de la requête
- binding session/projet
- réception d’attachements
- transport des réponses
- notifications

### Ce qu’elle ne doit pas comprendre
- logique universelle de compaction
- contrats métier profonds du kernel
- contenu architectural du projet

### Sous-plans
1. Définir un contrat `InboundRequest` normalisé.
2. Définir un contrat `OutboundPayload` normalisé.
3. Définir la liaison canal ↔ session ↔ projet actif.
4. Définir le transport des notifications entre canonique et branches.
5. Définir la remontée d’événements UI utiles.

### Fichiers likely to change
- `ROADMAP.md`
- `BRICKS.md`
- futur `marius/host/channels/*`
- futur `marius/host/router.py`

### Validation
- Le kernel reçoit une requête normalisée quel que soit le canal.
- Une même logique fonctionne pour CLI/web/Telegram.

---

## Brique 12 — `render_adapter`

### Rôle
Adapter le contenu logique aux contraintes de rendu de chaque surface.

### Ce qu’elle doit comprendre
- Markdown portable
- échappement / bloc code / diff block
- limitations de canal
- transformation diff → rendu visible
- notices de compaction → rendu visible

### Ce qu’elle ne doit pas comprendre
- logique universelle du kernel
- politique de compaction elle-même
- logique métier projet

### Sous-plans
1. Définir un format logique intermédiaire pour la sortie.
2. Définir la stratégie de rendu Markdown portable.
3. Définir les variantes de rendu par canal.
4. Définir le rendu d’un artefact `diff`.
5. Définir le rendu d’une notice de compaction.

### Fichiers likely to change
- `ROADMAP.md`
- `BRICKS.md`
- futur `marius/render/markdown.py`
- futur `marius/render/telegram.py`
- futur `marius/render/web.py`

### Validation
- Un même contenu logique reste lisible sur plusieurs surfaces.
- Le kernel n’a pas besoin de connaître Telegram ou HTML.

---

## Brique 13 — `notification_router`

### Rôle
Router les notifications entre session canonique et branches ciblées.

### Ce qu’elle doit comprendre
- source de notification
- cible
- politique de propagation
- granularité des événements

### Ce qu’elle ne doit pas comprendre
- rendu final du message
- logique provider
- compaction interne détaillée

### Sous-plans
1. Définir quels événements sont notifiables.
2. Définir quand une branche notifie la canonique.
3. Définir quand la canonique reste silencieuse.
4. Définir le contrat de notification minimal.
5. Définir les garde-fous anti-bruit.

### Fichiers likely to change
- `DECISIONS.md`
- `ROADMAP.md`
- futur `marius/host/notifications.py`

### Validation
- La canonique reçoit les signaux importants sans pollution.
- Les branches restent isolées par défaut.

---

## Brique 14 — `memory_store`

### Rôle
Stocker la mémoire durable utile, séparée des sessions courtes.

### Ce qu’elle doit comprendre
- mémoire générale
- mémoire projet
- recherche
- distinction local/global

### Ce qu’elle ne doit pas comprendre
- UI de consultation
- rendu des résultats
- logique provider spécifique

### Sous-plans
1. Définir la frontière mémoire générale / mémoire projet.
2. Définir la relation avec mode local/global.
3. Définir ce qui est mémoire durable vs résumé dérivé.
4. Définir la recherche simple et durable.
5. Définir le lien avec dreaming/daily.

### Fichiers likely to change
- `BRICKS.md`
- futur `marius/storage/memory.py`

### Validation
- Une branche projet ne contamine pas la mémoire générale par défaut.
- Les résumés dérivés ne remplacent pas les faits durables.

---

## Brique 15 — `runtime_orchestrator`

### Rôle
Assembler les briques dans le bon ordre à chaque tour.

### Ce qu’elle doit comprendre
- pipeline d’exécution
- séquencement minimal
- appel des interfaces des briques
- collecte des sorties structurées

### Ce qu’elle ne doit pas comprendre
- rendu final par canal
- persistance UI détaillée
- logique produit spécifique à une surface

### Sous-plans
1. Définir le pipeline canonique d’un tour.
2. Définir les points d’entrée/sortie des briques.
3. Définir où se branche le guard.
4. Définir où se branche la compaction.
5. Définir le format final remis au host.

### Fichiers likely to change
- `BRICKS.md`
- futur `marius/kernel/runtime.py`

### Validation
- Le runtime orchestre sans avaler les détails de canal.
- Le pipeline reste lisible et testable.

---

# Recommended implementation order

## Phase 1 — Verrouiller les frontières
1. `kernel_contracts`
2. `provider_adapter`
3. `security_guard`
4. `project_context`
5. `context_builder`

## Phase 2 — Verrouiller la session et la compaction
6. `session_runtime`
7. `compaction_engine`
8. `tool_router`
9. `artifact_store`
10. `ui_history_store`

## Phase 3 — Brancher les surfaces
11. `channel_host`
12. `render_adapter`
13. `notification_router`

## Phase 4 — Boucler le système
14. `memory_store`
15. `runtime_orchestrator`

---

# Files likely to change overall
- `BRICKS.md`
- `DECISIONS.md`
- `ROADMAP.md`
- futur document d’architecture détaillé, par ex. :
  - `ARCHITECTURE.md`
  - ou `docs/architecture/brick-boundaries.md`
- futurs packages :
  - `marius/kernel/*`
  - `marius/host/*`
  - `marius/render/*`
  - `marius/storage/*`

---

# Tests / validation plan

## Architecture checks
Pour chaque future brique, vérifier :
- peut-elle être importée seule ?
- connaît-elle un canal concret ?
- rend-elle de l’UI ?
- mélange-t-elle historique visible et contexte interne ?
- serait-elle réutilisable dans un autre assistant ?

## Cross-cutting validation
1. **Compaction**
   - réduit le contexte interne
   - ne casse pas l’historique visible
2. **Markdown cross-canaux**
   - même sens logique partout
   - rendu adapté par surface
3. **Diffs**
   - artefacts structurés
   - rendus correctement
   - reconsultables plus tard
4. **Branches / canonique**
   - isolation par défaut
   - notifications explicites

---

# Risks / tradeoffs
- **Trop de briques trop tôt** : risque de sur-segmentation théorique.
- **Kernel trop large** : on réintroduit un monolithe.
- **Kernel trop pauvre** : toute la logique fuit dans le host.
- **Confusion storage/UI** : surtout pour l’historique visible.
- **Confusion render/host** : surtout pour Markdown et diffs.

---

# Open questions
1. Faut-il garder `project_context` comme brique séparée de `context_builder` ?
2. Les artefacts doivent-ils être définis dans `kernel_contracts` ou dans une mini-couche partagée dédiée ?
3. Le `render_adapter` doit-il être standalone ou partie du `channel_host` ?
4. La session canonique doit-elle être un concept purement host, ou partiellement modélisé dans les contrats kernel ?
5. Le `ui_history_store` doit-il être totalement distinct du `session_runtime`, ou seulement une vue persistée spécialisée ?

---

# Recommended next move
Après validation de ce plan :
1. transformer `BRICKS.md` pour refléter ce découpage réel ;
2. compléter `DECISIONS.md` avec les frontières définitives ;
3. écrire un document d’architecture court avec un schéma des flux ;
4. seulement ensuite démarrer le squelette de code par phase.