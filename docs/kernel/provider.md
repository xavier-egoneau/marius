# provider_adapter

## Rôle

Définit le protocole d'accès à un provider LLM et fournit un double de test en mémoire. Les implémentations concrètes (HTTP) vivent dans `adapters/`.

## Couche

Kernel

## Standalone

Oui. Dépend uniquement de `kernel/contracts.py`.

## Dépendances

- `marius.kernel.contracts` — `Message`, `Role`, `ContextUsage`

## Interface publique

```python
@dataclass
class ProviderConfig:
    provider_name: str
    model: str

@dataclass
class ProviderRequest:
    messages: list[Message]
    metadata: dict

@dataclass
class ProviderResponse:
    message: Message          # role = ASSISTANT
    usage: ContextUsage
    provider_name: str
    model: str
    metadata: dict

class ProviderError(RuntimeError):
    provider_name: str
    retryable: bool

class ProviderAdapter(Protocol):
    def generate(self, request: ProviderRequest) -> ProviderResponse: ...

class InMemoryProviderAdapter:
    """Double de test : retourne une réponse fixe ou lève une erreur configurée."""
    calls: list[ProviderRequest]   # historique des appels pour assertions
```

## Usage — double de test

```python
from marius.kernel.provider import InMemoryProviderAdapter, ProviderConfig, ProviderError

adapter = InMemoryProviderAdapter(
    config=ProviderConfig(provider_name="test", model="stub"),
    completion_text="Réponse stub",
)
response = adapter.generate(ProviderRequest(messages=[...]))
assert response.message.content == "Réponse stub"
assert len(adapter.calls) == 1
```

## Invariants

- `ProviderAdapter` est un `Protocol` : toute classe avec `generate()` satisfait le contrat.
- `ProviderError.retryable` indique si le `RuntimeOrchestrator` peut retenter l'appel.
- Le double en mémoire suffit pour tester tout le kernel sans réseau.
