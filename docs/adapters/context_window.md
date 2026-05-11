# context_window (adapters)

## Rôle

Implémentation HTTP de la résolution de fenêtre de contexte via l'API d'un provider. Complète `kernel/context_window.py` pour la stratégie `API` en fournissant le callable injectable.

## Couche

Adapters

## Standalone

Oui. Dépend uniquement de stdlib (urllib, json). Aucun lien vers le reste de Marius.

## Dépendances

Aucune (stdlib uniquement).

## Interface publique

```python
def resolve_via_api(
    base_url: str,
    api_endpoint: str,
    model: str,
    *,
    api_key: str = "",
    timeout: int = 5,
) -> int | None
    # Retourne la fenêtre de contexte ou None si l'appel échoue.
    # Supporte le format Ollama : modelinfo["llama.context_length"]

def make_api_resolver(
    base_url: str,
    api_endpoint: str,
    model: str,
    *,
    api_key: str = "",
    timeout: int = 5,
) -> Callable[[], int | None]
    # Fabrique un callable sans argument pour injection dans kernel/context_window.
```

## Relation avec kernel/context_window

```
kernel/context_window.py
  resolve_context_window(model, strategy, api_resolver=None)
                                               ↑
                                    adapters/context_window.py
                                      make_api_resolver(...)
                                      → closure capturant base_url, endpoint, model
```

Le kernel ne sait pas comment la valeur est récupérée. L'adapter ne sait pas comment elle est utilisée. Le contrat est le callable `() → int | None`.

## Usage

```python
from marius.adapters.context_window import make_api_resolver
from marius.kernel.context_window import resolve_context_window

resolver = make_api_resolver(
    base_url="http://localhost:11434",
    api_endpoint="/api/show",
    model="llama3:latest",
)
window = resolve_context_window("llama3:latest", "api", api_resolver=resolver)
# → valeur Ollama, ou registre statique, ou 128k
```

## Format Ollama /api/show

```json
POST /api/show  {"name": "llama3"}
→ {
    "modelinfo": {
      "llama.context_length": 131072,
      "llama.embedding_length": 4096,
      ...
    }
  }
```

La brique cherche n'importe quelle clé contenant `"context_length"` dans `modelinfo` — flexible pour les futurs formats.

## Invariants

- `resolve_via_api` retourne `None` en cas d'erreur réseau, HTTP ou de parsing — jamais d'exception propagée.
- `timeout=5` par défaut — court volontairement pour ne pas bloquer le démarrage du REPL.
- `make_api_resolver` capture les arguments dans une closure — le callable retourné est sans état.
