# http_provider (adapters)

## Rôle

Implémentations HTTP concrètes du protocole `ProviderAdapter`. `make_adapter()` sélectionne la classe selon `ProviderDefinition.protocol` — ajouter un nouveau provider compatible OpenAI ne nécessite aucun nouveau fichier.

## Couche

Adapters

## Standalone

Oui. Dépend de `kernel/contracts`, `kernel/provider` et `provider_config/registry`. Stdlib uniquement pour le réseau (urllib).

## Dépendances

- `marius.kernel.contracts` — `Message`, `Role`, `ContextUsage`
- `marius.kernel.provider` — `ProviderAdapter` (Protocol), `ProviderRequest`, `ProviderResponse`, `ProviderError`
- `marius.provider_config.contracts` — `ProviderEntry`
- `marius.provider_config.registry` — `PROVIDER_REGISTRY`, `ProviderProtocol`

## Interface publique

```python
def make_adapter(entry: ProviderEntry) -> OpenAICompatibleAdapter | OllamaNativeAdapter
    # Factory basée sur defn.protocol.
    # Lève ValueError si le provider n'est pas dans PROVIDER_REGISTRY.

class OpenAICompatibleAdapter:
    # Protocole : OPENAI_COMPATIBLE
    # Endpoint  : {base_url}{defn.chat_endpoint}  (ex : /chat/completions)
    # Auth      : Authorization: Bearer {api_key}
    # Parsing   : response["choices"][0]["message"]["content"]
    # Usage     : response["usage"]["prompt_tokens"]
    def generate(self, request: ProviderRequest) -> ProviderResponse

class OllamaNativeAdapter:
    # Protocole : OLLAMA_NATIVE
    # Endpoint  : {base_url}{defn.chat_endpoint}  (ex : /api/chat)
    # Auth      : Bearer optionnel
    # Parsing   : response["message"]["content"]
    # Usage     : response["prompt_eval_count"]
    def generate(self, request: ProviderRequest) -> ProviderResponse
```

## Ajouter un nouveau provider compatible OpenAI

```python
# registry.py
PROVIDER_REGISTRY["mistral"] = ProviderDefinition(
    kind="mistral",
    label="Mistral AI",
    default_base_url="https://api.mistral.ai/v1",
    requires_api_key=True,
    protocol=ProviderProtocol.OPENAI_COMPATIBLE,   # ← même adapter
    chat_endpoint="/chat/completions",
    ...
)
# → make_adapter() retourne un OpenAICompatibleAdapter sans aucun changement de code
```

## Ajouter un nouveau protocole

Créer une nouvelle classe `XxxAdapter` ici, ajouter `XXX = "xxx"` dans `ProviderProtocol`, brancher dans `make_adapter()`.

## Gestion des erreurs

```python
class ProviderError(RuntimeError):
    provider_name: str
    retryable: bool   # True pour 429, 5xx — False pour 4xx non-429
```

Les erreurs réseau (`URLError`) sont marquées `retryable=True`. Les erreurs de parsing de réponse sont `retryable=False`.

## Invariants

- `make_adapter` s'appuie sur `defn.protocol`, jamais sur `entry.provider` directement.
- Les messages `TOOL_CALL` sont ignorés dans la conversion (`_ROLE_MAP` ne les inclut pas).
- `stream=False` — pas de streaming pour l'instant. Le streaming est une slice ultérieure.
