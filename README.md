# Marius

Marius est un assistant agentique local, modulaire et extensible. Il sait discuter,
utiliser des outils, travailler dans un projet, mémoriser des informations utiles,
exposer une interface web et se connecter à Telegram.

Le projet est encore en alpha, mais le socle est déjà utilisable en local :
CLI, gateway persistant, providers OpenAI/Ollama, outils fichier/shell/web/mémoire,
skills, dreaming, routines, interface web et canal Telegram.

## Ce que fait Marius

- Dialogue avec un LLM via un provider configurable.
- Lit, écrit et explore les fichiers du projet.
- Exécute des commandes shell sous contrôle de permissions.
- Recherche sur le web via SearxNG auto-hébergé.
- Garde une mémoire locale SQLite.
- Charge des skills depuis `~/.marius/skills`.
- Peut planifier et implémenter des tâches avec le skill `dev`.
- L'agent admin peut déléguer à des subagents isolés avec `spawn_agent`; les agents nommés peuvent aussi recevoir cet outil si besoin.
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
- un agent admin principal ;
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

Commandes fréquentes dans le REPL et dans les surfaces gateway/web/Telegram :

```text
/help       afficher les commandes
/context    afficher l'état du contexte
/new        démarrer une nouvelle conversation
/compact    compacter le contexte court
/remember   mémoriser un fait
/memories   lister les souvenirs
/forget     supprimer un souvenir
/doctor     diagnostiquer l'installation
/dream      consolider la mémoire
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
- `make_dir` : créer un dossier ;
- `move_path` : déplacer ou renommer un fichier ou dossier ;
- `explore_tree` : résumer l'arborescence d'un projet ;
- `explore_grep` : chercher du texte dans les fichiers avec chemins et lignes ;
- `explore_summary` : détecter les fichiers clés et métadonnées d'un projet ;
- `run_bash` : exécuter une commande shell ;
- `web_fetch` : récupérer une URL ;
- `web_search` : chercher via SearxNG ;
- `vision` : analyser une image locale via Ollama ;
- `skill_view` : lire le contenu d'un skill ;
- `skill_create` : créer un skill Markdown portable ;
- `skill_list` : lister les skills installés ;
- `skill_reload` : relire les skills depuis le disque et retourner un snapshot ;
- `host_agent_list` : lister les agents configurés sans exposer de secret provider ;
- `host_agent_save` : créer ou modifier un agent Marius ;
- `host_agent_delete` : supprimer un agent non principal avec confirmation explicite ;
- `host_telegram_configure` : configurer Telegram via référence de secret ;
- `host_status` : inspecter la config agents et l'état gateway/systemd ;
- `host_doctor` : lancer le diagnostic Marius et retourner le rapport structuré ;
- `host_logs` : lire les logs récents avec filtres optionnels ;
- `host_gateway_restart` : planifier un redémarrage gateway après confirmation ;
- `project_list` : lister les projets connus et le projet actif explicite ;
- `project_set_active` : définir le projet actif par chemin ou nom connu ;
- `approval_list` : lister les demandes de permissions récentes ;
- `approval_decide` : mémoriser une approbation ou un refus pour une demande ;
- `approval_forget` : oublier une décision mémorisée ;
- `secret_ref_list` : lister les références de secrets sans résoudre les valeurs ;
- `secret_ref_save` : enregistrer une référence `env:` ou `file:` nommée ;
- `secret_ref_delete` : supprimer une référence de secret ;
- `secret_ref_prepare_file` : créer un fichier secret local `0600` et l'enregistrer comme référence ;
- `provider_list` : lister les providers LLM sans exposer les clés ;
- `provider_save` : créer ou modifier un provider avec `api_key_ref` ;
- `provider_delete` : supprimer un provider après confirmation ;
- `provider_models` : récupérer les modèles disponibles d'un provider ;
- `dreaming_run` : consolider la mémoire via le moteur dreaming ;
- `self_update_propose` : enregistrer une proposition de mise à jour sans l'appliquer ;
- `self_update_report_bug` : enregistrer un bug exploitable pour une future mise à jour ;
- `self_update_list` : lister les propositions et bugs self-update ;
- `self_update_show` : relire une proposition ou un bug par identifiant ;
- `self_update_apply` : appliquer une proposition patchée après confirmation ;
- `self_update_rollback` : inverser une application self-update enregistrée ;
- `open_marius_web` : lancer l'interface web locale ;
- `rag_*` : gérer et interroger des sources Markdown locales ;
- `caldav_*` : diagnostiquer et lire un calendrier local `vdirsyncer`/`khal` ;
- `sentinelle_scan` : auditer localement services, ports, autostart et exposition Docker ;
- `spawn_agent` : déléguer une tâche à des subagents ;
- `memory` : gérer la mémoire durable ;
- `reminders` : créer, lister ou annuler des rappels via le gateway.

Les outils de mutation host/admin globale sont réservés au rôle `admin`. Les
agents nommés gardent leurs surfaces CLI/web/Telegram ; `spawn_agent` est
désactivé par défaut pour eux, mais peut être activé explicitement comme un
outil configurable.

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
le modèle reformule et décide de la suite. Le résumé affiché dans les traces
peut rester court ; le runtime réinjecte aussi les données structurées utiles au
modèle, avec masquage des clés sensibles évidentes.

## Recherche web avec SearxNG

Le tool `web_search` utilise SearxNG localement. Quand `web_search` est actif,
Marius tente de démarrer le service fourni au lancement du REPL ou du gateway :

```bash
docker compose -f docker-compose.searxng.yml up -d
```

Ce démarrage est best-effort : si Docker ou le compose file ne sont pas
disponibles, Marius continue à fonctionner et `web_search` retourne une erreur
claire. Pour désactiver cet auto-start :

```bash
export MARIUS_SEARCH_AUTO_START=0
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
~/.marius/projects.json               projets connus
~/.marius/active_project.json         projet actif explicite
~/.marius/approvals.json              audit et décisions de permissions
~/.marius/secret_refs.json            références de secrets nommées
~/.marius/self_updates/               propositions et bugs self-update
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

L'agent peut aussi consulter ces informations via les outils `host_status`,
`host_doctor` et `host_logs`, quand ils sont actifs dans sa configuration. Ces
outils sont read-only : ils donnent des observations au modèle, qui garde la
réponse finale.

Les actions host disponibles côté agent admin sont atomiques et passent par le
gardien de permissions : `host_agent_save`, `host_agent_delete` et
`host_telegram_configure`. Pour Telegram, le modèle ne doit jamais recevoir le
token brut ; l'outil accepte uniquement `token_ref` au format `env:NOM`,
`file:/chemin/token` ou `secret:NOM`.

## Sécurité administrable

Les demandes de permission peuvent être auditées via `approval_list`. Une
décision peut être mémorisée avec `approval_decide`, puis oubliée avec
`approval_forget`. Les arguments sensibles sont redacted dans le store.

Les secrets passent par des références nommées : `secret_ref_save` accepte
uniquement `env:NOM` ou `file:/chemin/token`, jamais une valeur brute. Les outils
ne retournent pas les valeurs résolues. Les actions comme Telegram peuvent
ensuite utiliser `token_ref: secret:<nom>`.

Pour créer une référence sans exposer la valeur dans le chat,
`secret_ref_prepare_file` prépare un fichier privé sous `~/.marius/secrets/`.
L'utilisateur y place ensuite la valeur localement ; Marius ne garde que la
référence `file:`.

Les providers configurés par l'agent suivent la même règle : `provider_save`
refuse les clés brutes et accepte `api_key_ref` (`env:`, `file:` ou `secret:`).
Les anciennes clés déjà présentes dans `~/.marius/marius_providers.json` restent
compatibles, mais elles sont masquées dans les sorties des tools.

## Self-update

Marius peut documenter ses propres évolutions sans les appliquer directement.
Les outils `self_update_propose` et `self_update_report_bug` créent des fichiers
Markdown dans `~/.marius/self_updates/`. Une proposition peut joindre un diff
comme artefact, mais l'application d'un patch reste une action séparée qui doit
être demandée explicitement par l'utilisateur.

`self_update_apply` exige une proposition existante, `confirm: true`, un patch
valide, un dépôt git contrôlé et un état de travail propre sauf exception
documentée (`allow_dirty`). Il applique le patch, lance des commandes de test
bornées (`pytest`, `python -m pytest`, `git diff --check`) et écrit un rapport.
`self_update_rollback` inverse le patch enregistré par `self_update_apply`.

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
skills et la configuration provider. Le web, le gateway, Telegram, dreaming,
les routines et les subagents sont fonctionnels mais encore en consolidation.
