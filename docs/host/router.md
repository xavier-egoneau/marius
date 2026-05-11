# host_router

## Rôle

Surface mince entre un canal concret et le runtime kernel. Transforme une requête entrante en `TurnInput`, orchestre le kernel, renvoie un `OutboundPayload` visible.

## Couche

Host

## Standalone

Oui. Peut servir de base à CLI, web et Telegram sans changer le noyau.

## Dépendances

- `marius.kernel.contracts` — `Message`, `Role`, `Artifact`
- `marius.kernel.runtime` — `RuntimeOrchestrator`, `TurnInput`
- `marius.kernel.session` — `SessionRuntime`
- `marius.render.adapter` — `render_message`
- `marius.storage.ui_history` — `InMemoryVisibleHistoryStore`, `VisibleHistoryEntry`

## Interface publique

```python
@dataclass
class InboundRequest:
    channel: str      # "cli" | "web" | "telegram"
    session_id: str
    peer_id: str
    text: str
    metadata: dict

@dataclass
class OutboundPayload:
    text: str         # texte rendu (Markdown portable)
    metadata: dict    # channel, peer_id, session_id, compaction_level…

class HostRouter:
    def __init__(
        self, *,
        orchestrator: RuntimeOrchestrator,
        history_store: InMemoryVisibleHistoryStore | None = None,
        sessions: dict[str, SessionRuntime] | None = None,
        system_prompt: str = "",
    )
    def route(self, request: InboundRequest) -> OutboundPayload
```

## Pipeline d'une requête

```
InboundRequest
  → _get_or_create_session()      crée ou récupère la SessionRuntime
  → history_store.append(user)    enregistre le message utilisateur
  → orchestrator.run_turn()       tour kernel complet
  → render_message(assistant)     Markdown portable
  → history_store.append(asst.)   enregistre la réponse
  → OutboundPayload
```

## Usage

```python
from marius.host.router import HostRouter, InboundRequest
from marius.kernel.runtime import RuntimeOrchestrator
from marius.kernel.provider import InMemoryProviderAdapter, ProviderConfig

adapter = InMemoryProviderAdapter(
    config=ProviderConfig("test", "stub"),
    completion_text="Réponse test",
)
router = HostRouter(
    orchestrator=RuntimeOrchestrator(provider=adapter),
    system_prompt="Tu es Marius.",
)
payload = router.route(InboundRequest(
    channel="cli", session_id="s1", peer_id="user", text="Bonjour"
))
print(payload.text)  # → "Réponse test"
```

## Invariants

- Le router ne possède pas la logique provider — il délègue au `RuntimeOrchestrator`.
- L'historique visible (`history_store`) reste séparé du contexte interne kernel.
- Si `assistant_message` est None (provider non branché), le fallback est `"Requête prête pour le provider."`.
- Chaque `session_id` distinct produit une `SessionRuntime` isolée.
