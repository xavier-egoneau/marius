# Marius — Architecture mémoire

## Vision

La mémoire de Marius n'est pas un cache de contexte — c'est un store de connaissance
persistant dont seul un sous-ensemble pertinent est injecté à chaque session.

Trois propriétés fondamentales :

1. **Le store est illimité** (SQLite) — le dreaming n'a pas à compresser pour survivre à
   une limite technique ; il organise et priorise.
2. **L'injection est bornée et sélective** — seul ce qui est pertinent *maintenant* entre
   dans le contexte actif : profil utilisateur + contexte du projet en cours.
3. **Le dreaming est la couche d'inférence** — seul un LLM peut distinguer
   "projet dormant mais stratégique" de "question éphémère et révolue".

---

## Store de mémoire (`memory.db`)

### Schéma

```sql
memories
├── memory_id    INTEGER PK
├── content      TEXT     -- le fait mémorisé
├── scope        TEXT     -- "global" | "project"
├── project_path TEXT     -- chemin absolu du projet (null si global)
├── category     TEXT     -- "user_profile" | "agent_notes" | "project" | ...
├── tags         TEXT     -- tags libres séparés par virgules
└── created_at   TIMESTAMP
```

### Scopes

| Scope | Contenu | Injection |
|-------|---------|-----------|
| `global` | Profil utilisateur, préférences cross-projets, faits durables de l'agent | Toujours, à chaque session |
| `project` | Contexte d'un projet précis, décisions locales, leçons apprises sur ce projet | Uniquement quand ce projet est le projet actif |

### Injection active

```python
contexte_actif = store.get_active_context(cwd)
# = global + project[cwd]
```

- Snapshot gelé à l'ouverture de session (stable pour toute la session, cache-friendly)
- Pas de recherche par tour : le contexte est déterministe
- Un projet dormant conserve toutes ses entrées — elles réapparaissent dès qu'il redevient actif

---

## Corpus de sessions (`~/.marius/sessions/`)

### Rôle

Source court-terme pour le dreaming. Les fichiers session ne sont **jamais injectés**
dans le contexte actif — ce sont des matières premières traitées puis archivées.

### Format

```
~/.marius/sessions/YYYY-MM-DD-HHhMM.md
```

```yaml
---
project: marius
cwd: /home/egza/Documents/projets/marius
opened_at: 2026-05-08T14:32:00Z
closed_at: 2026-05-08T16:14:00Z
turns: 23
---
```

Écrit automatiquement par le REPL à la fermeture de session (même Ctrl-D).
Contenu minimal : pointeur vers le projet et la fenêtre temporelle.
Le dreaming lit directement `DECISIONS.md` et `ROADMAP.md` du projet pour le contexte détaillé.

### Cycle de vie

```
session active → sessions/YYYY-MM-DD-HHhMM.md
                     ↓ dreaming
             sessions/archive/YYYY-MM-DD-HHhMM.md
```

Après traitement par le dreaming, les fichiers sont archivés (pas supprimés).

---

## System de skills (`~/.marius/skills/`)

### Structure d'un skill

```
~/.marius/skills/
└── agenda/
    ├── SKILL.md     ← instructions d'utilisation + config du skill
    └── dream.md     ← données que ce skill fournit au dreaming
```

### SKILL.md — frontmatter

```yaml
---
name: agenda
description: Accès au calendrier Google
version: 1.0.0
---
```

### dream.md — contrat dreaming

Déclare au dreaming les sources de données que ce skill peut fournir :
informations sur les événements passés, récurrences, projets planifiés.

### Skills système

Le dreaming est piloté par le runtime et les skills actifs :

```
~/.marius/skills/
└── dreaming/
    └── SKILL.md   ← config (heure cron, nb sessions à digérer, limites)
```

---

## Dreaming tool

### Déclenchement

- Manuel : `/dream` ou appel direct par l'agent
- Automatique : cron à l'heure configurée dans `dreaming/SKILL.md`
- Le cron démarre une session agent isolée et déclenche le tool

### Pipeline d'entrées

```
memory.db (scope=global + scope=project pour les projets récents)
sessions/*.md non traités
projets récents → project_store → DECISIONS.md + ROADMAP.md
skills actifs → dream.md de chaque skill
```

### Appel LLM

Un seul appel avec :
- L'état actuel du store (entrées existantes)
- Le corpus de sessions depuis le dernier dreaming
- Le contenu des fichiers projet pertinents
- Les instructions du skill `dreaming/SKILL.md`
- Les données déclarées par chaque `dream.md` de skill actif

### Sorties

```json
{
  "memory_ops": [
    { "op": "add",     "scope": "global",  "content": "...", "category": "user_profile" },
    { "op": "add",     "scope": "project", "project_path": "/...", "content": "..." },
    { "op": "replace", "memory_id": 42,    "content": "..." },
    { "op": "remove",  "memory_id": 17 }
  ],
  "notes": "Synthèse utile pour les prochains tours ou routines..."
}
```

- Opérations appliquées au store SQLite
- Handoff écrit dans `~/.marius/sessions/dreaming/YYYY-MM-DD.md`
- Sessions traitées déplacées dans `sessions/archive/`

### Philosophie de consolidation

Le dreaming **organise** plus qu'il ne compresse :
- Distingue global (durable, cross-projet) vs project (local, contextuel)
- Préserve les projets dormants mais stratégiques
- Éjecte l'éphémère (questions ponctuelles, états transitoires)
- Fusionne les doublons
- Peut être généreux dans ce qu'il garde — la sélectivité est à l'injection, pas au stockage

---

## Briefings par routines

Il n'y a pas de commande ni d'outil dédié au briefing.

Un briefing est une tâche récurrente ordinaire :

- le prompt de la routine décrit les sources à consulter et le format attendu ;
- la cadence de la task déclenche l'envoi au gateway ;
- l'agent compose la réponse avec les outils disponibles, comme dans une conversation normale.

Les données utiles vivent dans la mémoire, les sources RAG ou les outils métier.
La routine ne crée pas de second système de contexte.

---

## Project store (`~/.marius/projects.json`)

Registre des projets récemment ouverts. Mis à jour à chaque démarrage REPL.

```json
[
  {
    "path": "/home/egza/Documents/projets/marius",
    "name": "marius",
    "last_opened": "2026-05-08T14:32:00Z",
    "session_count": 12
  }
]
```

Source de vérité unique pour le dreaming : il interroge ce fichier pour savoir
quels projets inspecter (DECISIONS.md, ROADMAP.md).

---

## Gestion du contexte dans le temps

```
Sessions brutes        →  dreaming  →  store organisé
(bruit + signal)          (LLM)        (signal structuré)
     ↓                                       ↓
archivées                          injection sélective
                                   (global + project actif)
```

**Invariant** : la taille du contexte injecté ne croît pas avec le temps.
Le store peut croître librement ; l'injection reste bornée par le scope.

Un investissement ponctuel (appel LLM dreaming) achète une mémoire
plus pertinente et plus stable pour toutes les sessions futures.

---

## Ordre d'implémentation

1. **`project_store`** — persistance des projets récents + écriture auto du fichier session au REPL exit
2. **Skills reader** — lecture de `~/.marius/skills/*/SKILL.md` + `dream.md`
3. **Migration `memory_store`** — ajout des champs `scope` et `project_path`, méthode `get_active_context(cwd)`
4. **Dreaming tool** — agrège entrées, appel LLM, applique opérations JSON
5. **Routines** — tasks récurrentes avec prompt explicite
6. **Cron** — déclenche dreaming et routines aux heures configurées
