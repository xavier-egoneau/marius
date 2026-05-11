# Marius — Context Files

## But
Définir la répartition des fichiers Markdown de contexte pour éviter de tout faire reposer sur un seul document.

## Répartition cible

### 1. `SOUL.md`
**Portée** : par agent.

Contient :
- identité de l’agent,
- ton,
- posture,
- style d’interaction,
- frontières de personnalité.

Ne contient pas :
- règles spécifiques à un projet,
- décisions techniques locales,
- mémoire de l’utilisateur comme historique détaillé.

### 2. `USER.md`
**Portée** : par agent ou par workspace global.

Contient :
- contexte humain durable,
- préférences stables,
- repères relationnels utiles à long terme.

Ne contient pas :
- plan de projet,
- conventions de repo,
- détails temporaires d’une tâche.

### 3. `AGENTS.md`
**Portée** : par projet.

Contient :
- conventions de contribution,
- règles de vérification,
- commandes utiles,
- contraintes projet pour les agents futurs.

Ne contient pas :
- personnalité de l’agent,
- mémoire durable de l’utilisateur,
- historique conversationnel complet.

### 4. `DECISIONS.md`
**Portée** : par projet.

Contient :
- choix d’architecture durables,
- alternatives rejetées,
- impacts structurants.

### 5. `ROADMAP.md`
**Portée** : par projet.

Contient :
- checklist vivante,
- slices d’implémentation,
- statut vérifiable.

## Règle de séparation
- **Qui est l’agent ?** → `SOUL.md`
- **Qui est l’utilisateur ?** → `USER.md`
- **Comment travaille-t-on dans ce repo ?** → `AGENTS.md`
- **Qu’a-t-on décidé ?** → `DECISIONS.md`
- **Que reste-t-il à faire ?** → `ROADMAP.md`

## Conséquence produit
Le `context_builder` devra assembler ces couches sans les fusionner conceptuellement.

## Note sur les branches
Une branche ciblée peut avoir sa propre mémoire projet, mais n’a pas besoin d’un nouveau type de fichier Markdown tant qu’un simple rattachement projet + session suffit.
