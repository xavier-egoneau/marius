# compaction_engine

## Rôle

Calcule le niveau de compaction à appliquer selon l'usage de contexte et des seuils configurables. Ne modifie pas la session — se contente de signaler le niveau.

## Couche

Kernel

## Standalone

Oui. Aucune dépendance externe. Réutilisable dans tout runtime conversationnel.

## Dépendances

- `marius.kernel.contracts` — `ContextUsage`, `Message`

## Interface publique

```python
class CompactionLevel(str, Enum):
    NONE      # < 60% de la fenêtre
    TRIM      # 60–74% : supprimer les tours anciens
    SUMMARIZE # 75–89% : résumer le contexte par le LLM
    RESET     # ≥ 90% : réinitialiser complètement

@dataclass
class CompactionConfig:
    context_window_tokens: int = 250_000
    trim_threshold: float      = 0.60
    summarize_threshold: float = 0.75
    reset_threshold: float     = 0.90
    keep_recent_turns: int     = 10

def compaction_level(token_count: int, config: CompactionConfig) -> CompactionLevel
def resolve_token_count(usage: ContextUsage) -> int
def estimate_tokens_from_messages(messages: list[Message], *, chars_per_token: int = 4) -> int
def estimate_tokens_from_chars(char_count: int, *, chars_per_token: int = 4) -> int
def total_message_characters(messages: list[Message]) -> int
```

## Usage

```python
from marius.kernel.compaction import CompactionConfig, CompactionLevel, compaction_level
from marius.kernel.contracts import ContextUsage

config = CompactionConfig(context_window_tokens=128_000)
usage  = ContextUsage(provider_input_tokens=90_000)

level = compaction_level(90_000, config)
# → CompactionLevel.RESET  (90 000 / 128 000 = 70.3% → TRIM)
```

## Seuils (décision 2026-05-07)

| Niveau | Seuil | Action recommandée |
|--------|-------|--------------------|
| NONE | < 60% | Rien |
| TRIM | 60–74% | Supprimer les tours les plus anciens |
| SUMMARIZE | 75–89% | Résumer via un tour dédié au LLM |
| RESET | ≥ 90% | Réinitialiser le contexte interne |

## Invariants

- `resolve_token_count` préfère `provider_input_tokens` à l'estimation — si le provider renvoie un compte exact, il prime.
- L'estimation est à `chars / 4` — approximation volontairement conservative.
- Cette brique **signale** seulement le niveau. La décision d'action (trim, résumé, reset) appartient à la couche qui consomme le signal (`RuntimeOrchestrator`, `host/repl`).
- La compaction ne touche **jamais** l'historique visible utilisateur (`ui_history_store`).
