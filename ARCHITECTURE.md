# Marius — Architecture

## But
Donner une frontière nette entre les grandes couches de Marius v2 pour éviter que le système redevienne un monolithe implicite.

## Règle simple

- **Kernel** = logique universelle
- **Host** = adaptation runtime et canaux
- **Render** = présentation visible
- **Storage** = persistance spécialisée

Cette règle prime sur les découpages de fichiers tant qu’il n’existe pas encore de code stabilisé.

---

## 1. Kernel

Le kernel comprend la **signification universelle** d’un tour agentique.

### Responsabilités
- contrats de domaine (`Message`, `ToolCall`, `ToolResult`, `Artifact`, `PermissionDecision`, etc.)
- pipeline logique d’un tour
- protocole provider
- protocole permissions / approvals
- logique de session courte
- compaction du contexte interne
- estimation et suivi de l’usage de contexte
- assemblage logique du contexte
- statut sémantique des artefacts comme `diff`, `image`, `report`, `file`

### Le kernel ne doit pas comprendre
- Telegram, HTTP, WebSocket, TUI
- rendu Markdown final d’un canal
- HTML/UI web
- polling, routes, endpoints, boutons, panneaux
- historique visible utilisateur comme produit d’interface

### Règle spécifique compaction
- le kernel peut compacter le **contexte interne**
- le kernel ne doit pas effacer l’**historique visible utilisateur**
- le kernel peut produire des **résumés dérivés** et des **notices de compaction logiques**

---

## 2. Host

Le host comprend l’**adaptation au monde extérieur**.

### Responsabilités
- adapter les canaux concrets (CLI, web, Telegram)
- normaliser les requêtes entrantes
- binder une requête à une session et à un projet actif
- router les notifications
- ingérer les attachements
- transmettre au kernel un format stable
- transporter la réponse vers la bonne surface

### Le host ne doit pas comprendre
- logique universelle de compaction
- logique provider métier profonde
- rendu détaillé dépendant d’une UI spécifique si une couche render existe

---

## 3. Render

La couche render comprend la **présentation visible**.

### Responsabilités
- Markdown portable
- adaptation du rendu selon surface
- rendu des blocs `diff`
- rendu des notices de compaction
- regroupement visible des activités outils
- échappement / troncature / formats de code

### La couche render ne doit pas comprendre
- logique universelle du kernel
- sécurité
- persistance
- sélection de projet

---

## 4. Storage

La couche storage comprend la **persistance spécialisée**.

### Responsabilités
- session store logique
- ui history store
- memory store
- artifact store
- index et recherche
- conservation de la version source d’un artefact même si l’affichage est tronqué

### Point important
Le storage doit distinguer :
- **contexte interne compactable**
- **historique visible utilisateur**
- **artefacts persistants**

---

## 5. Invariants transverses

### Markdown cross-canaux
- le kernel produit un contenu logique portable
- le render adapte ce contenu à chaque surface
- le host le transporte

### Diffs
- les diffs sont des **artefacts structurés**
- ils ne sont pas seulement du texte brut
- ils peuvent être attachés à un tour ou à un résultat outil
- ils doivent pouvoir être persistés, relus et rendus proprement

### Compaction
- elle réduit la pression de contexte
- elle ne doit pas faire disparaître la conversation visible pour l’utilisateur
- elle peut s’appuyer sur une estimation heuristique ou sur des métriques provider plus fiables

### Modes local/global
- le mode local reste attaché au dossier
- le mode global porte la session canonique et la mémoire générale
- les branches ciblées restent isolées par défaut et notifient explicitement si besoin

---

## 6. Briques recommandées

### Kernel
- `kernel_contracts`
- `provider_adapter`
- `security_guard`
- `context_builder`
- `project_context`
- `session_runtime`
- `compaction_engine`
- `tool_router`
- `runtime_orchestrator`

### Host
- `channel_host`
- `notification_router`

### Render
- `render_adapter`

### Storage
- `artifact_store`
- `ui_history_store`
- `memory_store`

---

## 7. Test de frontière

Avant d’ajouter une responsabilité à une brique, poser ces questions :

1. Est-ce universel ou dépendant d’un canal ?
2. Est-ce une règle métier ou une règle d’affichage ?
3. Est-ce une logique temporaire de session ou une persistance durable ?
4. Cette brique pourrait-elle être réutilisée dans un autre assistant ?

Si la réponse pointe vers une surface, une UI, ou un transport concret, cela ne doit probablement pas aller dans le kernel.
