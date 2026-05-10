# Marius

Marius est un assistant agentique local, modulaire et extensible. Il sait discuter,
utiliser des outils, travailler dans un projet, mémoriser des informations utiles,
lancer des sous-agents, exposer une interface web et se connecter à Telegram.

Le projet est encore en alpha, mais le socle est déjà utilisable en local :
CLI, gateway persistant, providers OpenAI/Ollama, outils fichier/shell/web/mémoire,
skills, dreaming/daily, interface web et canal Telegram.

## Ce que fait Marius

- Dialogue avec un LLM via un provider configurable.
- Lit, écrit et explore les fichiers du projet.
- Exécute des commandes shell sous contrôle de permissions.
- Recherche sur le web via SearxNG auto-hébergé.
- Garde une mémoire locale SQLite.
- Charge des skills depuis `~/.marius/skills`.
- Peut planifier et implémenter des tâches avec le skill `dev`.
- Peut déléguer à des subagents isolés avec `spawn_agent`.
- Peut tourner comme gateway persistant et servir CLI, web et Telegram.

## Installation

Depuis le repo :

```bash
cd /chemin/vers/marius
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

Pré-requis :

- Python 3.11 ou plus récent.
- `rich` est installé par le package.
- Docker est optionnel, mais utile pour `web_search` avec SearxNG.
- Ollama est optionnel, utile pour un provider local ou l'outil vision.
- systemd user est optionnel, utile pour lancer le gateway au démarrage.

## Premier démarrage

Lance le wizard :

```bash
marius setup
```

Le setup configure :

- un provider LLM ;
- un agent principal ;
- le modèle utilisé ;
- les outils actifs ;
- les skills actifs ;
- le mode de permissions.

Les fichiers de configuration vivent dans `~/.marius/`.

## Providers LLM

Marius supporte actuellement :

- OpenAI compatible via clé API ;
- ChatGPT/OpenAI via OAuth navigateur ;
- Ollama en local.

Commandes utiles :

```bash
marius add provider       # ajouter un provider
marius edit provider      # modifier un provider
marius set model          # changer le modèle actif
marius config show        # voir la config de l'agent principal
```

Les providers sont stockés dans `~/.marius/marius_providers.json`.
Les clés API y sont stockées en clair pour l'instant.

## Utilisation CLI

Démarrer une session locale dans le dossier courant :

```bash
marius
```

Le dossier de lancement devient le projet de travail. Marius charge le contexte
utile, les skills actifs, la mémoire projet et les outils configurés.

Commandes fréquentes dans le REPL :

```text
/help       afficher les commandes
/context    afficher l'état du contexte
/new        démarrer une nouvelle conversation
/compact    compacter le contexte court
/remember   mémoriser un fait
/memories   lister les souvenirs
/dream      consolider la mémoire
/daily      générer le briefing du jour
/stop       interrompre l'inférence en cours
/exit       quitter
```

Les skills peuvent ajouter leurs propres commandes. Par exemple le skill `dev`
peut exposer `/plan`, `/dev`, `/test`, `/review`, `/commit`, `/resume`, `/pr`.

## Interface web

Démarrer l'interface web :

```bash
marius web
```

Par défaut, l'interface est disponible sur :

```text
http://localhost:8765
```

Changer de port :

```bash
marius web --port 8787
```

Redémarrer le gateway puis relancer le web :

```bash
marius restart
```

L'agent peut aussi ouvrir l'interface web via son outil `open_marius_web`, si cet
outil est actif dans sa configuration.

## Gateway persistant

Le gateway maintient une session d'agent en arrière-plan. Il est utilisé par le
web, Telegram et les sessions agent persistantes.

Commandes :

```bash
marius gateway start
marius gateway status
marius gateway stop
```

Pour lancer un agent nommé via le gateway :

```bash
marius --agent main
```

Le gateway nécessite le skill `assistant` sur l'agent ciblé :

```bash
marius skills activate assistant --agent main
```

## Service systemd

Sur Linux avec systemd user :

```bash
marius gateway install-service
marius gateway enable --agent main
marius gateway status
```

Désactiver :

```bash
marius gateway disable --agent main
```

Si tu veux que le service démarre sans session graphique ouverte, le doctor ou
la commande d'installation indiquera la commande `loginctl enable-linger`.

## Telegram

Configurer le canal Telegram :

```bash
marius telegram setup
```

Le wizard demande :

- le token BotFather ;
- les user IDs autorisés ;
- l'agent associé.

Voir l'état :

```bash
marius telegram status
```

Le bot démarre avec le gateway de l'agent configuré.

## Skills

Les skills vivent dans :

```text
~/.marius/skills/<nom-du-skill>/
```

Structure typique :

```text
SKILL.md          instructions générales du skill
DREAM.md          données utiles au dreaming, optionnel
DAILY.md          données utiles au daily, optionnel
core/<cmd>.md     prompt d'une commande slash, optionnel
```

Lister les skills :

```bash
marius skills list
```

Activer ou désactiver un skill :

```bash
marius skills activate dev --agent main
marius skills deactivate dev --agent main
```

Un skill peut définir des commandes dans le frontmatter de `SKILL.md` :

```markdown
---
name: dev
commands: plan, dev, test
---
```

Chaque commande correspond à un fichier `core/<commande>.md`.

## Outils disponibles

Les outils configurables incluent notamment :

- `read_file` : lire un fichier texte ;
- `list_dir` : lister un dossier ;
- `write_file` : écrire un fichier ;
- `run_bash` : exécuter une commande shell ;
- `web_fetch` : récupérer une URL ;
- `web_search` : chercher via SearxNG ;
- `vision` : analyser une image locale via Ollama ;
- `skill_view` : lire le contenu d'un skill ;
- `open_marius_web` : lancer l'interface web locale ;
- `spawn_agent` : déléguer une tâche à des subagents ;
- `memory` : gérer la mémoire durable.

Activer ou désactiver un outil :

```bash
marius config tool +open_marius_web
marius config tool -run_bash
```

Voir la configuration :

```bash
marius config show
```

## Permissions

Marius propose trois modes :

- `safe` : lecture locale, shell désactivé, écritures très limitées ;
- `limited` : écriture dans le projet, sorties de zone sur confirmation ;
- `power` : très permissif, avec quelques garde-fous système.

Le mode se choisit dans `marius setup`.

Les actions sensibles passent par un gardien de permissions. Les outils ne sont
pas censés remplacer la réponse du LLM : ils fournissent des observations, puis
le modèle reformule et décide de la suite.

## Recherche web avec SearxNG

Le tool `web_search` utilise SearxNG localement. Démarrer le service fourni :

```bash
docker compose -f docker-compose.searxng.yml up -d
```

URL par défaut :

```text
http://localhost:19080
```

Surcharge possible :

```bash
export MARIUS_SEARCH_URL=http://localhost:19080
```

## Mémoire, sessions et logs

Marius stocke ses données locales dans `~/.marius/`.

Chemins utiles :

```text
~/.marius/config.json                 config agents/outils/permissions
~/.marius/marius_providers.json       providers LLM
~/.marius/skills/                     skills installés
~/.marius/workspace/<agent>/memory.db mémoire SQLite
~/.marius/workspace/<agent>/sessions/ corpus de sessions
~/.marius/logs/marius.jsonl           logs de diagnostic
```

Voir les logs :

```bash
marius logs
marius logs --tail 200
marius logs --path
marius logs --clear
```

## Diagnostic

Lancer un diagnostic complet :

```bash
marius doctor
```

Le doctor vérifie :

- config Marius ;
- provider et modèle ;
- SearxNG ;
- fichiers système ;
- gateway.

## Développement

Installer en editable puis lancer les tests :

```bash
pip install -e .
pytest tests/ -q
```

Arborescence principale :

```text
marius/kernel/           logique agentique universelle
marius/host/             REPL et adaptation CLI
marius/channels/web/     interface web et serveur HTTP
marius/channels/telegram canal Telegram
marius/gateway/          processus persistant et protocole socket
marius/tools/            outils exposés au LLM
marius/storage/          mémoire, logs, sessions
marius/config/           configuration agents/outils
marius/provider_config/  configuration providers
marius/adapters/         adapters LLM concrets
marius/render/           rendu Markdown portable
```

Documentation technique :

- `ARCHITECTURE.md` : frontières kernel/host/render/storage ;
- `DECISIONS.md` : décisions durables ;
- `ROADMAP.md` : état et prochaines slices ;
- `docs/` : documentation des briques internes.

## Statut du projet

Marius est expérimental. Il vise une expérience plus fluide que rigide, plus
modulaire que monolithique, et plus lisible qu'intelligente à tout prix.

Les surfaces les plus stables aujourd'hui sont le CLI, le kernel, les tools, les
skills et la configuration provider. Le web, le gateway, Telegram, dreaming/daily
et les subagents sont fonctionnels mais encore en consolidation.
