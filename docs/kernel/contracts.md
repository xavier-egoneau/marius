# kernel_contracts

## Rôle

Définit les objets de domaine partagés entre toutes les briques de Marius. Aucune logique métier — uniquement des structures de données.

## Couche

Kernel

## Standalone

Oui. Aucune dépendance interne ni externe. Peut être embarqué tel quel dans tout autre projet agentique Python.

## Dépendances

Aucune (stdlib uniquement : `dataclasses`, `datetime`, `enum`).

## Interface publique

### Enums

```python
class Role(str, Enum):
    SYSTEM    # message système
    USER      # message utilisateur
    ASSISTANT # réponse du modèle
    TOOL_CALL # appel d'outil par le modèle
    TOOL      # résultat d'outil

class ArtifactType(str, Enum):
    DIFF / IMAGE / REPORT / FILE

class PermissionDecision(str, Enum):
    ALLOW / DENY / ASK
```

### Dataclasses

```python
@dataclass
class Message:
    role: Role
    content: str
    created_at: datetime
    correlation_id: str = ""
    visible: bool = True
    metadata: dict
    artifacts: list[Artifact]

@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict

@dataclass
class ToolResult:
    tool_call_id: str
    ok: bool | None
    summary: str
    data: dict
    artifacts: list[Artifact]
    error: str | None

@dataclass
class ContextUsage:
    estimated_input_tokens: int
    provider_input_tokens: int | None
    max_context_tokens: int | None

@dataclass
class CompactionNotice:
    level: str      # "trim" | "summarize" | "reset"
    summary: str
    metadata: dict

@dataclass
class Artifact:
    type: ArtifactType
    path: str
    data: dict
```

## Invariants

- `Message.visible = False` signale un message interne (system prompt, résumé de compaction) non destiné à l'historique UI.
- `ContextUsage.provider_input_tokens` prime sur `estimated_input_tokens` quand les deux sont présents.
- Les artefacts `DIFF` ont un rendu détaillé ; les autres ont au moins un fallback portable.
