# Marius — Documentation des briques

## Architecture

Marius est organisé en 4 couches strictes + 2 couches transverses :

```
kernel/          Logique universelle — aucune dépendance UI ou réseau
render/          Présentation visible — Markdown portable
storage/         Persistance — historique, artefacts, mémoire
host/            Adaptation canaux — CLI, web, Telegram

provider_config/ Configuration des providers LLM — wizard CLI standalone
adapters/        Implémentations concrètes HTTP — branchées sur les protocoles du kernel
```

## Règle de frontière

Avant d'ajouter une responsabilité à une brique :

1. Est-ce universel ou dépendant d'un canal ?
2. Est-ce une règle métier ou une règle d'affichage ?
3. Cette brique pourrait-elle être réutilisée dans un autre assistant ?

Si la réponse pointe vers une surface, une UI ou un transport concret → pas dans le kernel.

---

## Carte des briques

### Kernel

| Brique | Fichier | Rôle |
|--------|---------|------|
| [kernel_contracts](kernel/contracts.md) | `kernel/contracts.py` | Objets de domaine partagés |
| [provider_adapter](kernel/provider.md) | `kernel/provider.py` | Protocole provider + double de test |
| [session_runtime](kernel/session.md) | `kernel/session.py` | État conversationnel court |
| [compaction_engine](kernel/compaction.md) | `kernel/compaction.py` | Niveaux et seuils de compaction |
| [context_window](kernel/context_window.md) | `kernel/context_window.py` | Résolution de la fenêtre de contexte |
| [context_builder](kernel/context_builder.md) | `kernel/context_builder.py` | Assemblage des sources Markdown |
| [project_context](kernel/project_context.md) | `kernel/project_context.py` | Résolution du projet actif |
| [guardian_policy](kernel/guardian_policy.md) | `kernel/guardian_policy.py` | Politique d'extension de zone allow |
| [runtime_orchestrator](kernel/runtime.md) | `kernel/runtime.py` | Pipeline d'un tour agentique |

### Render

| Brique | Fichier | Rôle |
|--------|---------|------|
| [render_adapter](render/adapter.md) | `render/adapter.py` | Markdown portable cross-canaux |

### Storage

| Brique | Fichier | Rôle |
|--------|---------|------|
| [ui_history_store](storage/ui_history.md) | `storage/ui_history.py` | Historique visible utilisateur |

### Host

| Brique | Fichier | Rôle |
|--------|---------|------|
| [host_router](host/router.md) | `host/router.py` | Surface mince canal → kernel |
| [repl](host/repl.md) | `host/repl.py` | REPL interactif CLI |

### Provider Config

| Brique | Fichier | Rôle |
|--------|---------|------|
| [provider_config](provider_config/index.md) | `provider_config/` | Configuration wizard providers LLM |

### Adapters

| Brique | Fichier | Rôle |
|--------|---------|------|
| [http_provider](adapters/http_provider.md) | `adapters/http_provider.py` | Adapters HTTP OpenAI / Ollama |
| [context_window_adapter](adapters/context_window.md) | `adapters/context_window.py` | Résolution fenêtre via API provider |

---

## Lancer les tests

```bash
pytest tests/ -q
```

## Lancer le CLI

```bash
marius                  # démarre le REPL (wizard provider si non configuré)
marius add provider     # configurer un provider
marius edit provider    # modifier un provider
marius set model        # changer le modèle actif
```
