# Marius — Liste des briques standalone

## Règle générale
Chaque brique doit pouvoir être comprise, testée et réutilisée seule, avec un couplage faible au reste du système.

## Frontière de référence

- **Kernel** : logique universelle
- **Host** : adaptation runtime et canaux
- **Render** : présentation visible
- **Storage** : persistance spécialisée

Une brique ne doit pas mélanger plusieurs couches sans raison forte.

---

## Brique 1 — `kernel_contracts`

**Rôle**
- Définir les objets de domaine communs.

**Responsabilités**
- Messages, tours, tool calls, tool results.
- Permissions, approvals, événements.
- Artefacts structurés : `diff`, `image`, `report`, `file`.
- Notices de compaction et métadonnées de contexte.

**Dépendances autorisées**
- Types partagés.
- Validation légère.

**Dépendances interdites**
- Canal concret.
- UI.
- Provider spécifique.

**Standalone si**
- Un autre assistant peut réutiliser les mêmes contrats sans reprendre Telegram, web ou la CLI.

---

## Brique 2 — `provider_adapter`

**Rôle**
- Normaliser l’accès aux providers LLM.

**Responsabilités**
- Auth.
- Generate synchrone minimal d’abord, puis stream si besoin réel.
- Erreurs provider.
- Remontée d’usage : tokens, limites, métriques si disponibles.

**Dépendances autorisées**
- Transport réseau.
- Contrats provider.

**Dépendances interdites**
- Projet actif.
- UI.
- Workflow dev.

**Standalone si**
- On peut le brancher à un autre runtime agentique sans connaître Marius.
- Un double en mémoire suffit pour le tester sans réseau.

---

## Brique 3 — `security_guard`

**Rôle**
- Filtrer les actions sensibles.

**Responsabilités**
- Évaluer une intention d’action.
- Produire `allow`, `deny`, `ask`.
- Gérer un minimum de politique et de TTL d’approbation.

**Dépendances autorisées**
- Politique de sécurité.
- Descripteurs d’action.

**Dépendances interdites**
- Rendu utilisateur détaillé.
- Canal concret.
- Logique provider profonde.

**Standalone si**
- Il peut s’insérer entre n’importe quel agent et une action sensible.

---

## Brique 4 — `context_builder`

**Rôle**
- Assembler le contexte logique à envoyer au LLM.

**Responsabilités**
- Lire les Markdown pertinents.
- Prioriser mémoire, décisions, repères projet.
- Produire un contexte compact et déclaratif.

**Dépendances autorisées**
- Lecture de fichiers `.md`.
- Métadonnées de session et de projet.

**Dépendances interdites**
- Appel provider.
- UI.
- Heuristique agressive de navigation projet.

**Standalone si**
- On peut l’employer dans un autre assistant piloté par des documents Markdown.

---

## Brique 5 — `project_context`

**Rôle**
- Porter la règle du projet actif.

**Responsabilités**
- Distinguer projet actif et projets cités.
- Porter les règles local/global.
- Décrire le contexte d’une branche ciblée.

**Dépendances autorisées**
- Métadonnées projet.
- Documents projet.

**Dépendances interdites**
- UI de sélection.
- Provider.
- Rendu.

**Standalone si**
- La même convention peut être reprise par un autre système multi-projets.

---

## Brique 6 — `session_runtime`

**Rôle**
- Gérer l’état conversationnel court.

**Responsabilités**
- Identifier une session.
- Grouper les tours.
- Lier messages, activités outils et artefacts.
- Préparer l’entrée de la compaction.

**Dépendances autorisées**
- Contrats kernel.
- Stockage léger abstrait.

**Dépendances interdites**
- Historique UI comme produit.
- Transport de canal.

**Standalone si**
- On peut piloter la continuité d’un assistant sans UI spécifique.

---

## Brique 7 — `compaction_engine`

**Rôle**
- Réduire le contexte interne quand la fenêtre devient tendue.

**Responsabilités**
- Estimer ou lire l’usage de contexte.
- Déclencher trim / summarize / reset.
- Produire résumé dérivé et notice logique.
- Préserver la distinction entre contexte compacté et historique visible.

**Dépendances autorisées**
- `provider_adapter` pour usage ou résumé si nécessaire.
- Contrats de session.

**Dépendances interdites**
- Suppression de l’historique visible utilisateur.
- Rendu de la notice.
- Spécificité Telegram/web.

**Standalone si**
- On peut l’utiliser dans un autre runtime conversationnel.

---

## Brique 8 — `tool_router`

**Rôle**
- Exposer et exécuter les outils disponibles.

**Responsabilités**
- Lister les outils.
- Router un appel vers une implémentation.
- Normaliser `ToolResult`.
- Attacher des artefacts structurés.

**Dépendances autorisées**
- Contrats outils.
- Guard si nécessaire.

**Dépendances interdites**
- UI.
- Rendu final.
- Logique métier couplée à un canal.

**Standalone si**
- Il reste réemployable avec d’autres outils.

---

## Brique 9 — `runtime_orchestrator`

**Rôle**
- Assembler les briques kernel dans le bon ordre.

**Responsabilités**
- Enchaîner contexte, provider, tools, guard, compaction.
- Produire une sortie structurée pour le host.

**Dépendances autorisées**
- Interfaces des autres briques kernel.

**Dépendances interdites**
- UI.
- Canal concret.
- Persistance visible détaillée.

**Standalone si**
- Il reste un assemblage fin et lisible.

---

## Brique 10 — `channel_host`

**Rôle**
- Adapter Marius aux canaux concrets.

**Responsabilités**
- CLI, web, Telegram.
- Normaliser les requêtes entrantes.
- Binder session et projet actif.
- Transporter réponses et attachements.

**Dépendances autorisées**
- Contrats d’entrée/sortie.
- APIs de canal.

**Dépendances interdites**
- Logique universelle de compaction.
- Rendu détaillé si une brique render existe.

**Standalone si**
- Un canal peut être ajouté ou retiré sans casser le kernel.
- Le host web peut rester léger, sans imposer FastAPI tant que les besoins produit n’en dépendent pas.

---

## Brique 11 — `notification_router`

**Rôle**
- Router les notifications entre session canonique et branches.

**Responsabilités**
- Définir ce qui remonte à la canonique.
- Éviter le bruit.
- Garder l’isolation des branches par défaut.

**Dépendances autorisées**
- Host.
- Métadonnées de session.

**Dépendances interdites**
- Rendu final.
- Provider.

**Standalone si**
- Il peut être remplacé sans toucher au kernel.

---

## Brique 12 — `render_adapter`

**Rôle**
- Adapter le contenu logique aux surfaces visibles.

**Responsabilités**
- Markdown portable.
- Échappement.
- Rendu des `diff`.
- Rendu des notices de compaction.
- Variantes CLI/web/Telegram.

**Dépendances autorisées**
- Contrats de sortie.
- Contraintes de surface.

**Dépendances interdites**
- Logique métier du kernel.
- Stratégie de compaction elle-même.

**Standalone si**
- Il peut rendre les mêmes objets pour plusieurs surfaces.

---

## Brique 13 — `artifact_store`

**Rôle**
- Conserver les artefacts structurés.

**Responsabilités**
- Stockage des diffs, rapports, fichiers, images.
- Lien avec session / tour / outil.
- Conservation de la version source complète même si l’affichage est tronqué.

**Dépendances autorisées**
- Persistance locale.
- Index légers.

**Dépendances interdites**
- UI.
- Provider.

**Standalone si**
- Un autre système peut réutiliser le store pour ses propres artefacts.

---

## Brique 14 — `ui_history_store`

**Rôle**
- Préserver l’historique visible utilisateur.

**Responsabilités**
- Vue append-only des messages visibles.
- Réinjection des notices utiles.
- Activités outils visibles.
- Références aux artefacts affichables.

**Dépendances autorisées**
- Contrats de message.
- Storage.

**Dépendances interdites**
- Logique provider.
- Politique de compaction interne.

**Standalone si**
- Il peut conserver une vue utilisateur sans dépendre d’une UI unique.

---

## Brique 15 — `memory_store`

**Rôle**
- Stocker la mémoire durable utile.

**Responsabilités**
- Mémoire générale.
- Mémoire projet.
- Recherche simple.
- Distinction local/global.

**Dépendances autorisées**
- Persistance locale.
- Schéma minimal.

**Dépendances interdites**
- UI.
- Rendu.
- Provider concret.

**Standalone si**
- Il peut être repris tel quel dans un autre assistant local.

---

## Critère d’acceptation global
Une brique est valide si :
- elle est réutilisable ;
- elle est testable seule ;
- elle n’aspire pas des responsabilités d’une autre couche ;
- elle garde le LLM au centre de l’expérience conversationnelle ;
- elle aide à préserver la lisibilité du système.
