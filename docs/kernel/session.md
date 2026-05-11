# session_runtime

## Rôle

Gère l'état conversationnel court d'une session : tours, messages, artefacts, résumés de compaction. Prépare le contexte pour le provider sans connaître les canaux ni l'historique visible.

## Couche

Kernel

## Standalone

Oui. Dépend uniquement de `kernel/contracts.py`.

## Dépendances

- `marius.kernel.contracts` — `Message`, `Role`, `Artifact`, `ToolResult`, `CompactionNotice`

## Interface publique

```python
@dataclass
class TurnRecord:
    id: str
    input_messages: list[Message]
    started_at: datetime
    assistant_message: Message | None
    tool_results: list[ToolResult]
    artifacts: list[Artifact]
    metadata: dict

@dataclass
class SessionState:
    session_id: str
    turns: list[TurnRecord]
    compaction_notices: list[CompactionNotice]
    derived_context_summary: str
    derived_context_summary_message: Message | None
    metadata: dict

class SessionRuntime:
    def __init__(self, *, session_id: str, metadata: dict = {})

    def start_turn(self, *, user_message: Message, metadata: dict = {}) -> TurnRecord
    def finish_turn(self, turn_id: str, *, assistant_message: Message = None) -> TurnRecord
    def attach_tool_result(self, turn_id: str, result: ToolResult) -> TurnRecord

    def register_compaction_summary(self, summary: str, *, notice: CompactionNotice = None)

    def internal_messages(
        self, *,
        include_summary: bool = False,
        include_tool_results: bool = False,
        recent_turn_limit: int | None = None,
    ) -> list[Message]
```

## Usage

```python
from marius.kernel.session import SessionRuntime
from marius.kernel.contracts import Message, Role
from datetime import datetime, timezone

session = SessionRuntime(session_id="main")
turn = session.start_turn(user_message=Message(
    role=Role.USER, content="Bonjour", created_at=datetime.now(timezone.utc)
))
session.finish_turn(turn.id, assistant_message=Message(
    role=Role.ASSISTANT, content="Bonjour !", created_at=datetime.now(timezone.utc)
))

messages = session.internal_messages()  # → [user_msg, assistant_msg]
```

## Invariants

- `start_turn` n'accepte que des messages avec `role = USER`.
- `finish_turn` n'accepte que des messages avec `role = ASSISTANT`.
- `internal_messages` retourne le contexte interne compactable — **jamais l'historique visible UI** (celui-ci vit dans `storage/ui_history`).
- Les artefacts d'un tour sont dédupliqués automatiquement à chaque mise à jour.
- `register_compaction_summary` injecte un message `SYSTEM visible=False` dans le contexte sans effacer les tours.
