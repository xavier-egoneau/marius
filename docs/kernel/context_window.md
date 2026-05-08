# context_window

## Rôle

Résout la taille de fenêtre de contexte d'un modèle LLM selon une stratégie déclarée. Fournit un registre statique des fenêtres connues et délègue les appels réseau à la couche adapter via injection.

## Couche

Kernel

## Standalone

Oui. Zéro dépendance réseau, zéro dépendance provider. L'accès réseau éventuel est injecté via un callable (`api_resolver`).

## Dépendances

Aucune (stdlib uniquement).

## Interface publique

```python
FALLBACK_CONTEXT_WINDOW: int = 128_000

def resolve_static(model: str) -> int | None
    # Exact match d'abord, puis match par préfixe pour les variantes versionées.
    # Ex : "gpt-4o-2024-05-13" → préfixe "gpt-4o" → 128 000

def resolve_context_window(
    model: str,
    strategy: str,               # "static" | "api" | "web_search" | "fallback"
    *,
    api_resolver: Callable[[], int | None] | None = None,
) -> int
    # Retourne toujours un entier > 0.
```

## Stratégies

| Stratégie | Comportement |
|-----------|-------------|
| `static` | Cherche dans le registre statique, fallback 128k si absent |
| `api` | Appelle `api_resolver()`, puis registre statique, puis fallback |
| `web_search` | Non implémenté — retourne le fallback en attendant la recherche web |
| `fallback` | Retourne `FALLBACK_CONTEXT_WINDOW` directement |

## Registre statique (extrait)

| Modèle | Fenêtre |
|--------|---------|
| gpt-5.4 | 250 000 |
| gpt-5 | 1 000 000 |
| gpt-4o | 128 000 |
| gpt-4 | 8 192 |
| gpt-3.5-turbo | 16 385 |
| o1 / o3 | 200 000 |

## Usage

```python
from marius.kernel.context_window import resolve_context_window

# Stratégie statique — pas de réseau
window = resolve_context_window("gpt-4o", "static")
# → 128 000

# Stratégie API — resolver injecté par la couche adapter
from marius.adapters.context_window import make_api_resolver
resolver = make_api_resolver("http://localhost:11434", "/api/show", "llama3")
window = resolve_context_window("llama3", "api", api_resolver=resolver)
# → valeur retournée par Ollama, ou registre statique, ou 128k
```

## Invariants

- Retourne toujours un entier ≥ 1.
- La stratégie `api` tente toujours le registre statique comme filet si le resolver échoue.
- Le callable `api_resolver` ne reçoit aucun argument — toutes les dépendances sont capturées dans la closure (voir `adapters/context_window.py`).
- `web_search` est reconnu mais non implémenté : quand la recherche web sera disponible, cette branche sera complétée sans changer le contrat.
