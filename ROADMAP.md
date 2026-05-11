# Marius — Roadmap

## État actuel (2026-05-11)

Le socle agentique est opérationnel en CLI :
kernel complet · provider ChatGPT OAuth + Ollama · tools filesystem/shell/web/memory ·
vision Ollama locale · permissions safe/limited/power · mémoire SQLite+FTS5 avec scopes ·
session corpus · logs locaux · onboarding skill · config agents · SearxNG auto-hébergé ·
observations courtes de session · postures agent conditionnelles ·
skills reader + skill_view + marius skills CLI · gateway (socket Unix, session persistante) ·
interface web · canal Telegram · service systemd user · dreaming + daily (LLM direct,
/dream /daily) · skill dev (plan/dev/commit/review/test/resume/pr) · subagents dev ·
outil `open_marius_web` · host diagnostics/action tools (`host_status`, `host_doctor`,
`host_logs`, `host_agent_*`, `host_telegram_configure`, `host_gateway_restart`) · self-update proposal tools
· persistent watch topics · projet actif explicite (`project_list`, `project_set_active`)
· commandes dev projet (`/projects`, `/project`, `/tasks`, `/decision`, `/check`)
· approvals/secrets administrables · provider config tools · dreaming/daily ToolEntry
· artefacts cross-canaux via rendu de sortie de tour commun · skills utilisateur migrés
`caldav_calendar`, `sentinelle` · RAG Markdown v1 (`rag_source_*`,
`rag_search`, `rag_get`, `rag_promote_to_memory`)

---

## Reste à faire

### 0. Écarts hérités de Maurice

Audit source : repo local `/home/egza/Documents/projets/Maurice`, notamment `README.md`,
`docs/architecture.md`, `docs/turn-lifecycle.md`, `maurice/host/cli.py` et
`maurice/system_skills/*/skill.yaml`.

Cette section ne décrit pas une feature livrable. Elle garde seulement les écarts
utiles repérés pendant l'audit ponctuel de la v1, pour vérifier que Marius ne
perd pas de capacités importantes tout en conservant sa logique v2.

- [x] **Parité coeur agentique** — boucle provider/tools, permissions, session courte,
      compaction, filesystem (lecture/liste/écriture/mkdir/move), shell, web fetch/search,
      vision, mémoire injectée, skills chargés, gateway, web, Telegram, dreaming/daily,
      dev workers.
- [x] **Host/admin diagnostics** — porter la tranche read-only du skill Maurice `host` :
      `host_status`, `host_doctor`, `host_logs`, en gardant le modèle responsable de la
      reformulation finale.
- [x] **Host/admin actions sensibles initiales** — porter `host_agent_list`,
      `host_agent_save`, `host_agent_delete` et `host_telegram_configure` avec garde
      de permissions et secret Telegram par `token_ref` (`env:` / `file:`), jamais
      par token brut dans le chat.
- [x] **Host/admin actions restantes** — compléter la suite modulaire du skill Maurice
      `host` : agents CRUD avancé, configuration providers, capture générique de secrets
      hors modèle, et ergonomie de redémarrage gateway.
- [x] **Approvals et secrets administrables** — ajouter une brique standalone pour lister,
      approuver/refuser et auditer les demandes sensibles persistantes, ainsi qu'une
      capture de secrets par référence (`env:` / `file:` / `secret:`), sans exposer
      les valeurs au modèle.
- [x] **Configuration providers depuis l'agent** — porter une surface tool sûre
      `provider_list`, `provider_save`, `provider_delete`, `provider_models`, branchée
      sur `~/.marius/marius_providers.json`, avec `api_key_ref` obligatoire pour les
      nouveaux secrets et compatibilité des anciennes clés.
- [x] **Skill authoring tools** — porter l'équivalent de `skills.create`, `skills.list`
      et `skills.reload` pour créer/recharger des skills utilisateur depuis l'agent,
      pas seulement via CLI.
- [x] **Self-update proposal flow initial** — remplacer le TODO vague `marius update`
      par un flux proposition-only : `self_update_propose`, `self_update_report_bug`,
      `self_update_list`, `self_update_show`, avec Markdown persistant, test plan,
      risques et diff optionnel en artefact, sans application automatique.
- [x] **Self-update apply/rollback explicites** — ajouter une suite séparée qui applique
      uniquement après accord explicite, garde un rapport, lance les tests et documente
      rollback.
- [x] **Veille persistante initiale** — porter les watch topics façon Marius :
      `watch_add`, `watch_list`, `watch_remove`, `watch_run`, store JSON standalone,
      rapports persistés, contribution au dreaming/daily sans recherche web cachée.
- [x] **Veille automatisée initiale** — brancher les topics non manuels au scheduler
      assistant avec cadences (`hourly`, `daily`, `weekly`, `Nm`, `Nh`, `Nd`),
      déduplication par URL et notifications Telegram opt-in via tag `notify`/`telegram`.
- [x] **Veille avancée** — améliorer la qualité des rapports : scoring de nouveauté,
      résumé LLM par topic, configuration fine des notifications et backfill contrôlé.
- [x] **Explore tools** — ajouter des outils standalone `tree`, `grep` et `summary`
      (`explore_tree`, `explore_grep`, `explore_summary`) sans dépendre du shell.
- [x] **Commandes projet Maurice** — compléter le skill dev ou un skill projet avec
      `/projects`, `/project`, `/tasks`, `/decision`, `/check` en plus de
      `/plan`, `/dev`, `/test`, `/review`, `/commit`, `/resume`, `/pr`, adossées aux
      tools génériques `project_list` et `project_set_active`.
- [x] **Daily/dreaming comme ToolEntry optionnels** — exposer `dreaming_run` et
      `daily_digest` au modèle quand c'est utile, tout en gardant `/dream`, `/daily`
      et le scheduler comme surfaces directes.
- [x] **Rappels complets** — l'outil Marius crée des rappels, mais doit aussi lister
      et annuler les rappels comme Maurice (`reminders.list`, `reminders.cancel`).
- [x] **Mémoire consultable par outil** — exposer recherche/liste/get mémoire au modèle,
      en plus de l'injection de contexte et de l'écriture `memory`.
- [x] **Skills utilisateur Maurice utiles** — porter les capacités utiles en skills
      Marius Markdown-first, avec outils natifs testés quand l'ancien skill avait
      du code. `todos` a été remplacé par RAG Markdown.
- [ ] **Provider parity restante** — décider et implémenter ou déprioriser Anthropic et
      Ollama remote/cloud, présents dans le setup Maurice.
- [ ] **Workspace dreaming collectif** — décider puis porter, si le multi-agents devient
      central, la synthèse des mémoires/projets récents de chaque agent workspace.
- [ ] **CLI parity utile** — comparer puis porter les commandes Maurice utiles :
      agents CRUD, models CRUD/default/assign/worker, auth status/logout, approvals
      list/approve/deny, scheduler configure/run-once/serve, monitor snapshot/events,
      migration Jarvis si encore pertinente.
- [x] **Migration `todos` vers RAG** — supprimer le skill/outillage `todos` dédié ;
      les listes et notes Markdown passent par les sources RAG.

### 1. Skills system

- [x] **Skills reader** — découverte et chargement de `~/.marius/skills/*/SKILL.md`
      dans le contexte système au démarrage REPL
- [x] **skill_view tool** — l'agent peut lire le contenu d'un skill à la demande
- [x] **DREAM.md / DAILY.md / core/** — parsing des contrats et commandes par skill
- [x] **`marius skills`** CLI — lister les skills disponibles, les activer par agent
- [x] **Commandes REPL depuis les skills** — frontmatter `commands:` + `core/<cmd>.md`
- [ ] **AGENTS.md global** — créer `~/.marius/AGENTS.md` conventions par défaut
- [ ] **SOUL.md auto-création** — générer un SOUL.md minimal au premier setup si absent

---

### 2. Mémoire — Dreaming & Daily

- [x] **Observations courtes de session** — faits vérifiés par les outils
      injectés au tour suivant sans persister dans `memory.db`
- [x] **Dreaming** — agrège memory.db + DREAM.md des skills + DECISIONS/ROADMAP
      → appel LLM unique → opérations JSON appliquées au store
- [x] **Daily** — mémoires + DAILY.md des skills → briefing Markdown (appel LLM direct)
- [x] **Archive sessions** — fichiers session archivés après dreaming
- [x] **Commandes REPL** `/dream`, `/daily` — déclenchement manuel
- [x] **Contenu des sessions dans le corpus** — sauvegarder un transcript lisible
      (user + assistant, sans tool calls) pour que le dreaming puisse analyser les conversations,
      pas seulement le store mémoire
- [x] **Rapport de dream persisté** — sauvegarder chaque dream en JSON
      (`~/.marius/dreams/dream_<ts>.json`) ; le daily lit le dernier rapport
      au lieu de recalculer depuis zéro
- [x] **Cron scheduling** — scheduler dans le gateway (jobs.json persistant, reprise après
      redémarrage, poll 60s, `dream_time`/`daily_time` dans `AgentConfig`, daily mis en cache)

---

### 3. Setup & config

- [ ] **`marius setup` validation** — tester le parcours complet first-run
- [ ] **SOUL.md dans le wizard** — proposer de remplir le style de l'agent au setup
- [ ] **`/decisions` et `/roadmap`** — charger DECISIONS.md / ROADMAP.md dans le REPL
- [ ] **`marius config --list-agents`** — afficher les agents configurés
- [ ] **Commande `/config`** dans le REPL — reconfigurer un agent en live

---

### 4. Skill assistant (bloc gateway)

Toutes ces fonctionnalités sont interdépendantes — elles s'activent ensemble.

- [x] **Skill système `assistant` minimal** — active IDENTITY.md / USER.md
      + onboarding conditionnel sans l’imposer au socle local
- [x] **Posture dev agent** — charge `~/.marius/agents/<agent>/postures/dev.md`
      uniquement quand la posture dev est active
- [x] **Gateway** — processus persistant (daemon/service) qui maintient une session
      active entre les relances
- [x] **Service système** — service systemd user template (`marius-gateway@.service`),
      `marius gateway install-service` / `enable` / `disable` / `status` (avec état systemd).
      Conditionné au skill `assistant` — `marius --agent X` et `gateway start/enable`
      bloqués avec message clair si le skill n'est pas activé.
- [ ] **Multi-agents** — plusieurs agents nommés gérés par le gateway
- [x] **Workspace** — `~/.marius/workspace/<agent>/` par agent, avec mémoire dédiée
- [ ] **USER.md wizard** — remplir le profil utilisateur via le skill onboarding
      (aujourd'hui géré par l'onboarding skill, wizard dédié à terme)
- [ ] **Notifications inter-agents** — une branche peut notifier la session principale

---

### 5. Subagents

Un agent peut spawner des subagents pour déléguer une tâche ciblée.
Le subagent tourne en isolation, rend son résultat au parent, puis s'arrête.

- [x] **`spawn_agent` tool** — workers délégués bornés (depth=1, max 5/appel, timeout 5min,
      contexte minimal task+fichiers, rapport structuré status/summary/changed_files/blocker).
      Le worker qui a besoin de plus de parallélisme retourne `needs_arbitration` —
      l'orchestrateur spawne alors de nouveaux workers (pas de récursion directe).
- [x] **Lifecycle worker** — éphémère, sans mémoire propre, auto-deny permissions interactives,
      cancel_event pour timeout, limite d'itérations d'outils.
- [x] **Skill `dev`** — `/plan` `/dev` `/commit` `/review` `/test` `/resume` `/pr`
      + tâches `[parallélisable]` / `[dépend de: X]` dans PLAN.md.
- [ ] **Exécution asynchrone** — notification gateway quand un worker long se termine
      (adapté aux builds, test suites, refactors lourds).

---

### 6. Canaux

- [x] **Host web** — API HTTP mince + interface web minimale (chat)
- [x] **Canal Telegram** — polling long (stdlib, pas de dépendance externe), thread intégré
      dans le gateway, turn_lock pour sérialiser CLI + Telegram sur la même session.
      Push daily automatique si chat_id mémorisé.
- [x] **Commandes Telegram** — `/start` `/help` `/new` `/daily` `/status`
- [x] **`marius telegram setup`** — wizard (token BotFather, allowed_users, agent)
- [x] **`marius telegram status`** — affiche bot username, agent, users autorisés
- [x] **Multi-canal** — même session accessible depuis CLI, web et Telegram
- [x] **Artefacts cross-canaux** — diffs, notices de compaction lisibles dans tous les canaux
- [x] **Rendu Markdown** — tester la cohérence entre CLI (rich), web (HTML) et Telegram

---

### 7. Outillage CLI

- [x] **`marius doctor`** — diagnostic de l'installation : provider joignable ?
      SearxNG actif ? config valide ? permissions cohérentes ? SOUL.md présent ?
      Affiche un rapport clair avec les correctifs suggérés.
- [ ] **`marius dashboard`** — vue synthétique de l'état courant : agents configurés,
      sessions récentes, taille mémoire, dernière exécution dreaming/daily,
      SearxNG status. Inspiré du dashboard Maurice.
- [ ] **`marius update`** — mise à jour de Marius lui-même

---

### 8. Hardening & production

- [ ] **Fichiers sensibles** — détecter `.env`, `.netrc`, clés SSH → alerte avant lecture/écriture
- [ ] **Récupération d'erreurs** — provider down, autres backends down → messages clairs + retry
- [ ] **Compaction streaming** — déclencher la compaction dans le chemin streaming
- [x] **Tests web tools** — tests unitaires pour `web_fetch` et `web_search`
- [x] **Tests memory tool** — tests pour `make_memory_tool` + intégration
- [ ] **Tests config** — tests pour `ConfigStore`, `run_setup`

---

## Principes de conduite

- Chaque brique doit être standalone et testable seule.
- Le LLM orchestre — les outils servent, n'imposent pas.
- La complexité s'ajoute par besoin réel, pas par anticipation.
- La sécurité passe avant la commodité.
