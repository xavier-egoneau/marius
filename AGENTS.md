# Marius — AGENTS.md

## Rôle du système
Marius doit rester un système agentique modulaire, lisible et réutilisable.

## Instructions pour tout contributeur humain ou agent

- Lire `DECISIONS.md` avant de changer l’architecture.
- Lire `ROADMAP.md` avant de commencer une tâche.
- Préférer les changements petits et ciblés.
- Éviter les abstractions inutiles.
- Garder le LLM au centre de l’interface conversationnelle.
- Faire passer les actions sensibles par le gardien de sécurité.
- Garder les briques standalone quand c’est possible.
- Si un choix d’architecture devient durable, l’inscrire dans `DECISIONS.md`.
- Si une tâche modifie la trajectoire du projet, mettre à jour `ROADMAP.md`.

## Conventions

- Le contexte projet doit être explicite.
- Les fichiers Markdown portent les intentions et les règles.
- Le code porte l’exécution.
- Les outils ne doivent pas produire des réponses de remplacement si le LLM doit reformuler.
- Les tests kernel se lancent avec `pytest tests/ -q` depuis la racine du repo.
- `SOUL.md` porte l’identité de l’agent ; `USER.md` le contexte humain durable ; `AGENTS.md` les conventions du projet.
- Le host web doit rester une surface mince au-dessus du runtime, pas une source de vérité concurrente.
- Le `provider_adapter` se développe en mode minimal d’abord : génération synchrone + usage + erreur normalisée avant le streaming.
- Le `render_adapter` retourne d’abord du Markdown portable (`str`) à partir des contrats kernel avant toute divergence spécifique par canal.
- Les artefacts `diff` ont un rendu détaillé ; les autres artefacts gardent au moins un fallback visible portable.
- Le `context_builder` assemble des sources Markdown explicites dans un ordre déclaré ; il ne découvre pas seul le projet actif.
- Le `project_context` résout explicitement le projet actif, les projets cités et le scope canonique/projet/branche avant d’alimenter le `context_builder`.

## Objectif de qualité
Le système doit être :
- plus fluide que strict
- plus modulaire que monolithique
- plus réutilisable que spécifique
- plus lisible que “intelligent à tout prix”
