# runtime_orchestrator

## Rôle

Assemble les briques kernel dans l'ordre d'un tour agentique : préparation du contexte, estimation de compaction, appel provider (optionnel), mise à jour de la session.

## Couche

Kernel

## Standalone

Oui. Assemblage fin et lisible des briques kernel — ne connaît ni UI ni canal.

## Dépendances

- `marius.kernel.contracts` — `Message`, `Role`, `ContextUsage`, `CompactionNotice`, `ToolResult`
- `marius.kernel.session` — `SessionRuntime`
- `marius.kernel.compaction` — `CompactionConfig`, `compaction_level`, `resolve_token_count`
- `marius.kernel.provider` — `ProviderAdapter`, `ProviderRequest`, `ProviderError`

## Interface publique

```python
@dataclass
class TurnInput:
    session: SessionRuntime
    user_message: Message
    system_prompt: str = ""
    usage: ContextUsage | None = None
    metadata: dict = {}

@dataclass
class TurnOutput:
    context_messages: list[Message]
    assistant_message: Message | None     # None si provider non branché
    tool_results: list[ToolResult]
    usage: ContextUsage
    compaction_notice: CompactionNotice | None
    metadata: dict                        # status, session_id, turn_id, compaction_level…

class RuntimeOrchestrator:
    def __init__(
        self, *,
        compaction_config: CompactionConfig | None = None,
        provider: ProviderAdapter | None = None,
    )
    def run_turn(self, turn_input: TurnInput) -> TurnOutput
```

## Pipeline d'un tour

```
1. session.start_turn(user_message)
2. session.internal_messages()  →  context_messages
3. si system_prompt : prepend Message(SYSTEM)
4. estimer / résoudre token_count
5. compaction_level(token_count, config)  →  compaction_notice si level != NONE
6. si provider branché :
     provider.generate(ProviderRequest)  →  ProviderResponse
     session.finish_turn(assistant_message)
7. retourner TurnOutput
```

## Usage

```python
from marius.kernel.runtime import RuntimeOrchestrator, TurnInput
from marius.kernel.session import SessionRuntime
from marius.kernel.provider import InMemoryProviderAdapter, ProviderConfig

adapter = InMemoryProviderAdapter(
    config=ProviderConfig("test", "stub"),
    completion_text="Bonjour !",
)
orchestrator = RuntimeOrchestrator(provider=adapter)
session = SessionRuntime(session_id="demo")

output = orchestrator.run_turn(TurnInput(
    session=session,
    user_message=Message(role=Role.USER, content="Salut", created_at=...),
    system_prompt="Tu es Marius.",
))
print(output.assistant_message.content)  # → "Bonjour !"
print(output.metadata["compaction_level"])  # → "none"
```

## Invariants

- Si `provider=None`, `TurnOutput.assistant_message` est `None` et `metadata["status"] == "ready_for_provider"`.
- Si le provider lève une `ProviderError`, le tour est marqué en erreur et l'exception est propagée.
- La fenêtre de contexte réelle (`usage.max_context_tokens`) prime sur le défaut statique de `CompactionConfig`.
- `compaction_notice` est produit mais aucune action de compaction n'est déclenchée ici — c'est la responsabilité du host.
