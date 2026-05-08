# Marius — Roadmap

## État actuel (2026-05-08)

Le socle agentique est opérationnel en CLI :
kernel complet · provider ChatGPT OAuth + Ollama · tools filesystem/shell/web/memory ·
vision Ollama locale · permissions safe/limited/power · mémoire SQLite+FTS5 avec scopes · session corpus ·
logs locaux · onboarding skill · config agents · SearxNG auto-hébergé
observations courtes de session non persistantes
postures agent conditionnelles

---

## Reste à faire

### 1. Skills system

- [ ] **Skills reader** — découverte et chargement de `~/.marius/skills/*/SKILL.md`
      dans le contexte système au démarrage REPL
- [ ] **skill_view tool** — l'agent peut lire le contenu d'un skill à la demande
- [ ] **dream.md / daily.md** — parsing des contrats de données par skill
- [ ] **`marius skills`** CLI — lister les skills disponibles, les activer par agent
- [ ] **AGENTS.md global** — créer `~/.marius/AGENTS.md` conventions par défaut
- [ ] **SOUL.md auto-création** — générer un SOUL.md minimal au premier setup si absent

---

### 2. Mémoire — Dreaming & Daily

- [x] **Observations courtes de session** — faits vérifiés par les outils
      injectés au tour suivant sans persister dans `memory.db`
- [ ] **Dreaming tool** — agrège sessions + memory.db + DECISIONS.md/ROADMAP.md
      + dream.md des skills actifs → appel LLM unique → opérations JSON sur le store
- [ ] **Daily tool** — handoff dreaming + daily.md des skills → briefing Markdown
- [ ] **Cron scheduling** — déclenche dreaming/daily aux heures configurées dans leurs skills
- [ ] **Archive sessions** — déplacer les fichiers session traités dans `sessions/archive/`
- [ ] **Commandes REPL** `/dream`, `/daily` — déclencher manuellement

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
- [ ] **Service système** — démarrage au boot ou au lancement de session
      (systemd user service ou launchd)
- [ ] **Multi-agents** — plusieurs agents nommés gérés par le gateway
- [ ] **Workspace** — `~/.marius/workspace/<agent>/` par agent, avec mémoire dédiée
- [ ] **USER.md wizard** — remplir le profil utilisateur via le skill onboarding
      (aujourd'hui géré par l'onboarding skill, wizard dédié à terme)
- [ ] **Notifications inter-agents** — une branche peut notifier la session principale

---

### 5. Subagents

Un agent peut spawner des subagents pour déléguer une tâche ciblée.
Le subagent tourne en isolation, rend son résultat au parent, puis s'arrête.

- [ ] **`spawn_agent` tool** — l'agent parent crée un subagent nommé avec une instruction,
      des tools restreints et un contexte dédié. Retourne le résultat final du subagent.
- [ ] **Lifecycle subagent** — démarrage, exécution, retour de résultat, nettoyage.
      Le subagent est éphémère : pas de session persistante, pas de mémoire propre.
- [ ] **Config héritée** — le subagent hérite du provider et du mode de permission du parent,
      sauf override explicite (ex : subagent read-only en mode safe).
- [ ] **Exécution synchrone** — le parent attend le résultat avant de continuer
      (adapté aux tâches courtes : analyse, recherche, rédaction).
- [ ] **Exécution asynchrone** — le parent reçoit une notification gateway quand c'est prêt
      (adapté aux tâches longues : build, test suite, refactor).
- [ ] **Skills catalogue — skill `dev`** — active les commandes REPL dédiées au développement :
      `/plan` planification, `/dev` implémentation, `/commit` commit guidé,
      `/review` revue de code, `/test` lancement + analyse des tests.
      Un skill peut déclarer des commandes REPL dans son frontmatter SKILL.md ;
      le REPL les enregistre au chargement du skill.

---

### 6. Canaux

- [ ] **Host web** — API HTTP mince + interface web minimale (chat)
- [ ] **Canal Telegram** — réception et envoi de messages via Bot API
- [ ] **Commandes Telegram** — `/start`, `/help`, `/status`, `/new`, commandes customs
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
