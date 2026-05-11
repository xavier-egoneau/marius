# Plan : combler la parite utile façon Marius

## Branche
`feature/marius-parity-tools` — à créer depuis `main`

## Hors scope
- Ne pas recopier l'architecture Maurice ni ses noms internes quand Marius a une convention plus simple.
- Ne pas ajouter de réponse directe d'outil qui remplace la reformulation finale du modèle.
- Ne pas implémenter les gros blocs `host`, `self_update` ou `veille` en vrac dans cette tranche.
- Ne pas changer le contrat de gateway ou de provider hors nécessité.

## Tâches
- [x] Ajouter les opérations filesystem standalone `make_dir` et `move_path`.
- [x] Étendre l'outil mémoire avec `search`, `list` et `get` sans casser `add`, `replace`, `remove`.
- [x] Étendre l'outil rappels avec `list` et `cancel`, en gardant `create` compatible avec l'appel actuel.
- [x] Mettre à jour le registre, les labels de traces et les tests des outils concernés.
- [x] Mettre à jour `ROADMAP.md` pour cocher uniquement les écarts réellement couverts.
- [x] Lancer `pytest tests/ -q` et documenter la prochaine tranche utile.
- [x] Ajouter les outils d'exploration standalone `explore_tree`, `explore_grep`, `explore_summary`.
- [x] Brancher les outils explore dans la config, le registre, les permissions et les traces.
- [x] Tester les outils explore et la migration de config associée.
- [x] Ajouter les outils Markdown-first `skill_create`, `skill_list`, `skill_reload`.
- [x] Brancher les outils skill authoring dans la config, le registre, les permissions et les traces.
- [x] Tester la création, la liste, le reload et la migration de config associée.
- [x] Ajouter les outils host/admin read-only `host_status`, `host_doctor`, `host_logs`.
- [x] Brancher les outils host/admin dans la config, le registre, les permissions et les traces.
- [x] Tester les diagnostics host, les logs filtrés et la migration de config associée.
- [x] Ajouter les actions host/admin initiales `host_agent_list`, `host_agent_save`,
      `host_agent_delete`, `host_telegram_configure`.
- [x] Refuser les tokens Telegram bruts et accepter seulement les références de secret
      `env:` / `file:`.
- [x] Tester les actions agents, la configuration Telegram, le guard et la migration.
- [x] Ajouter le flux self-update proposition-only `self_update_propose`,
      `self_update_report_bug`, `self_update_list`, `self_update_show`.
- [x] Persister les propositions/bugs en Markdown et exposer les diffs joints comme artefacts.
- [x] Refuser toute demande d'application automatique dans le tool self-update.
- [x] Ajouter la veille persistante `watch_add`, `watch_list`, `watch_remove`, `watch_run`.
- [x] Persister topics et rapports de veille dans `~/.marius/watch/`.
- [x] Injecter les derniers rapports de veille dans le contexte dreaming/daily.
- [x] Brancher les topics non manuels au scheduler gateway.
- [x] Ajouter la déduplication par URL et les notifications Telegram opt-in.
- [x] Ajouter un rendu commun de sortie de tour pour préserver diffs, rapports et notices
      de compaction en CLI, web/gateway et Telegram.
- [x] Tester le rendu Markdown réel côté CLI Rich, web HTML et Telegram, avec diffs
      et code inline.
- [x] Ajouter `host_gateway_restart` en redémarrage différé pour laisser la réponse finale partir.
- [x] Ajouter `secret_ref_prepare_file` pour préparer un fichier secret privé sans valeur brute dans le chat.
- [x] Ajouter `self_update_apply` sur proposition patchée, avec confirmation, git check,
      tests bornés et rapport d'application.
- [x] Ajouter `self_update_rollback` qui inverse uniquement une application enregistrée.
- [x] Ajouter la veille avancée : scoring de nouveauté, résumé LLM injecté, réglages
      de notification et backfill contrôlé via `dedupe: false`.
- [x] Vérifier le chemin agentique gateway/web avec tool calls réels, streaming final,
      rapport Markdown de veille et résumé visible dans l'observation outil.
- [x] Aligner les commandes slash de base sur le gateway/web/Telegram : `/help`,
      `/remember`, `/memories`, `/forget`, `/doctor`, `/dream`, `/daily`, `/context`,
      `/compact`.
- [x] Démarrer SearxNG au lancement de Marius quand `web_search` est actif, avec
      fallback best-effort et logs de diagnostic.
- [x] Réinjecter les `ToolResult` structurés au provider (`summary`, `data`,
      artefacts bornés) pour que le modèle puisse exploiter les résultats
      d'outils sans court-circuiter la réponse finale.

## Prochaines tranches
- Setup first-run : tester le parcours `marius setup` complet et corriger les éventuels
  écarts de configuration initiale.
