# Marius — Roadmap

## État actuel (2026-05-09)

Le socle agentique est opérationnel en CLI :
kernel complet · provider ChatGPT OAuth + Ollama · tools filesystem/shell/web/memory ·
vision Ollama locale · permissions safe/limited/power · mémoire SQLite+FTS5 avec scopes ·
session corpus · logs locaux · onboarding skill · config agents · SearxNG auto-hébergé ·
observations courtes de session · postures agent conditionnelles ·
skills reader + skill_view + marius skills CLI · gateway (socket Unix, session persistante) ·
dreaming + daily (LLM direct, /dream /daily) · skill dev (plan/dev/commit/review/test/resume/pr)

---

## Reste à faire

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
- [ ] **Contenu des sessions dans le corpus** — sauvegarder un transcript lisible
      (user + assistant, sans tool calls) pour que le dreaming puisse analyser les conversations,
      pas seulement le store mémoire
- [ ] **Rapport de dream persisté** — sauvegarder chaque dream en JSON
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
- [ ] **Gateway** — processus persistant (daemon/service) qui maintient une session
      active entre les relances
- [x] **Service système** — service systemd user template (`marius-gateway@.service`),
      `marius gateway install-service` / `enable` / `disable` / `status` (avec état systemd).
      Conditionné au skill `assistant` — `marius --agent X` et `gateway start/enable`
      bloqués avec message clair si le skill n'est pas activé.
- [ ] **Multi-agents** — plusieurs agents nommés gérés par le gateway
- [ ] **Workspace** — `~/.marius/workspace/<agent>/` par agent, avec mémoire dédiée
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

- [ ] **Host web** — API HTTP mince + interface web minimale (chat)
- [x] **Canal Telegram** — polling long (stdlib, pas de dépendance externe), thread intégré
      dans le gateway, turn_lock pour sérialiser CLI + Telegram sur la même session.
      Push daily automatique si chat_id mémorisé.
- [x] **Commandes Telegram** — `/start` `/help` `/new` `/daily` `/status`
- [x] **`marius telegram setup`** — wizard (token BotFather, allowed_users, agent)
- [x] **`marius telegram status`** — affiche bot username, agent, users autorisés
- [ ] **Multi-canal** — même session accessible depuis CLI, web et Telegram
- [ ] **Artefacts cross-canaux** — diffs, notices de compaction lisibles dans tous les canaux
- [ ] **Rendu Markdown** — tester la cohérence entre CLI (rich), web (HTML) et Telegram

---

### 7. Outillage CLI

- [ ] **`marius doctor`** — diagnostic de l'installation : provider joignable ?
      SearxNG actif ? config valide ? permissions cohérentes ? SOUL.md présent ?
      Affiche un rapport clair avec les correctifs suggérés.
- [ ] **`marius dashboard`** — vue synthétique de l'état courant : agents configurés,
      sessions récentes, taille mémoire, dernière exécution dreaming/daily,
      SearxNG status. Inspiré du dashboard Maurice.
- [ ] **`marius update`** — mise à jour de Marius lui-même

---

### 8. Hardening & production

- [ ] **Fichiers sensibles** — détecter `.env`, `.netrc`, clés SSH → alerte avant lecture/écriture
- [ ] **Récupération d'erreurs** — provider down, SearxNG down → messages clairs + retry
- [ ] **Compaction streaming** — déclencher la compaction dans le chemin streaming
- [ ] **Tests web tools** — tests unitaires pour `web_fetch` et `web_search`
- [ ] **Tests memory tool** — tests pour `make_memory_tool` + intégration
- [ ] **Tests config** — tests pour `ConfigStore`, `run_setup`

---

## Principes de conduite

- Chaque brique doit être standalone et testable seule.
- Le LLM orchestre — les outils servent, n'imposent pas.
- La complexité s'ajoute par besoin réel, pas par anticipation.
- La sécurité passe avant la commodité.
