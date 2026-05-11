# repl

## Rôle

REPL interactif en ligne de commande. Affiche le dashboard de bienvenue, gère la boucle de conversation, dispatche les commandes slash, déclenche l'auto-compaction, stream les tokens.

## Couche

Host

## Standalone

Non — assemble `adapters`, `kernel`, `provider_config`, `render` et `storage`.

## Dépendances

- `marius.adapters.http_provider` — `make_adapter`
- `marius.adapters.context_window` — `make_api_resolver`
- `marius.kernel.context_builder` — `ContextBuilder`, `ContextBuildInput`, `ContextSource`
- `marius.kernel.compaction` — `CompactionConfig`, `compaction_level`
- `marius.kernel.context_window` — `resolve_context_window`
- `marius.kernel.runtime` — `RuntimeOrchestrator`, `TurnInput`
- `marius.kernel.session` — `SessionRuntime`
- `marius.kernel.tool_router` — `ToolRouter`
- `marius.provider_config` — `ProviderEntry`, `ProviderStore`, `PROVIDER_REGISTRY`
- `marius.provider_config.wizard` — `run_add_provider`, `run_set_model`
- `marius.storage.ui_history` — `InMemoryVisibleHistoryStore`, `VisibleHistoryEntry`
- `marius.tools` — `READ_FILE`, `LIST_DIR`, `WRITE_FILE`, `RUN_BASH`
- `rich` — couleurs, spinner, Markdown, layout

## Interface publique

```python
def launch() -> None
    # Point d'entrée depuis cli.py.
    # Vérifie la config provider → wizard si absent → run_repl().

def run_repl(
    entry: ProviderEntry,
    store: ProviderStore | None = None,
    *,
    history: InMemoryVisibleHistoryStore | None = None,
    verbose: bool = False,
) -> None
    # Boucle REPL principale. `history` injectable pour les tests.
```

## Chargement du contexte

Le system_prompt est assemblé au démarrage depuis deux couches :

```
~/.marius/SOUL.md       identité de l'agent              (global, toujours)
~/.marius/USER.md       contexte utilisateur durable     (global, toujours)
~/.marius/AGENTS.md     conventions générales            (global, toujours)
{cwd}/AGENTS.md         conventions projet               (surcharge le global si présent)
```

`DECISIONS.md` et `ROADMAP.md` ne sont pas chargés automatiquement — ils sont trop volumineux et trop spécifiques au workflow actif. Ils seront accessibles via `/decisions` et `/roadmap` (à venir).

## Commandes disponibles

| Commande | Action |
|----------|--------|
| `/model` | Changer le modèle actif |
| `/provider` | Ajouter un provider |
| `/context` | Tokens, %, niveau de compaction |
| `/compact` | Trim manuel |
| `/new` | Réinitialiser la session |
| `/verbose` | Toggle affichage détaillé des outils |
| `/help` | Liste toutes les commandes |
| `/exit` / `/stop` | Quitter |
| `Ctrl-D` / `Ctrl-C` | Quitter |

## Streaming

Les réponses texte sont streamées token par token. Le spinner s'arrête dès le premier delta. Les réponses LLM sont affichées en Markdown natif (rich).

## Mode verbose

Quand actif (`/verbose` ou `verbose=True` à l'init) : l'output de chaque outil est affiché en citation Markdown `>` (300 chars max).

## Historique visible

Chaque tour enregistre dans `InMemoryVisibleHistoryStore` :
- `role="user"` — message saisi
- `role="tool"` — trace outil (`● Lecture  src/main.py`) avec métadonnées `{tool_name, target, ok, summary}`
- `role="assistant"` — réponse finale du LLM

## Auto-compaction

Après chaque tour, si `tokens / context_window >= 0.80`, trim silencieux (garde les N derniers tours).

## Testabilité

```python
history = InMemoryVisibleHistoryStore()
run_repl(entry, history=history, verbose=True)
traces = [e for e in history.list_entries("default") if e.role == "tool"]
```

## Bootstrap

```
marius
  ↓ launch()
  ├─ ProviderStore vide → run_add_provider() → relecture
  └─ entries[0] → run_repl(entry)
                    ├─ _build_system_prompt(cwd)   # 2 couches Markdown
                    ├─ _resolve_window(entry)       # fenêtre de contexte
                    └─ boucle REPL
```
