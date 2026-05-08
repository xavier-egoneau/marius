# ui_history_store

## Rôle

Conserve l'historique visible utilisateur dans une vue append-only, indépendante du contexte interne du kernel. Garantit que la compaction du contexte n'efface jamais ce que l'utilisateur a vu.

## Couche

Storage

## Standalone

Oui. Aucune dépendance vers le kernel ou les canaux.

## Dépendances

Aucune (stdlib uniquement).

## Interface publique

```python
@dataclass
class VisibleHistoryEntry:
    role: str                        # "user" | "assistant" | "system"
    content: str
    metadata: dict = {}
    artifacts: list[dict] = []       # sérialisés (type, path, data)

class InMemoryVisibleHistoryStore:
    def append(self, session_id: str, entry: VisibleHistoryEntry) -> None
    def get(self, session_id: str) -> list[VisibleHistoryEntry]
    def clear(self, session_id: str) -> None
    def all_session_ids(self) -> list[str]
```

## Usage

```python
from marius.storage.ui_history import InMemoryVisibleHistoryStore, VisibleHistoryEntry

store = InMemoryVisibleHistoryStore()
store.append("session-1", VisibleHistoryEntry(role="user", content="Bonjour"))
store.append("session-1", VisibleHistoryEntry(role="assistant", content="Bonjour !"))

history = store.get("session-1")
# → [VisibleHistoryEntry(role="user", ...), VisibleHistoryEntry(role="assistant", ...)]
```

## Séparation kernel / historique visible

```
SessionRuntime.internal_messages()    ← contexte interne compactable
InMemoryVisibleHistoryStore           ← historique visible, append-only, jamais compacté
```

Ces deux vues évoluent indépendamment. Après une compaction, le contexte interne est réduit mais l'historique visible reste intact.

## Invariants

- Append-only — pas de modification ni de suppression d'entrées existantes.
- `clear()` est réservé aux réinitialisations explicites de session (`/new`), pas à la compaction.
- Cette brique ne connaît ni logique provider, ni politique de compaction interne.
