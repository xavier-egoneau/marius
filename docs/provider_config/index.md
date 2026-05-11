# provider_config

## Rôle

Brique standalone de configuration des providers LLM. Fournit le wizard CLI interactif (`marius add provider`, `marius edit provider`, `marius set model`), la persistance dans `~/.marius/marius_providers.json`, la récupération des modèles disponibles et le flow OAuth PKCE pour ChatGPT.

## Couche

Transverse (ni kernel ni host — utilisable dans tout projet Python).

## Standalone

Oui. Dépend uniquement de `rich` (couleurs CLI) et de stdlib. Zéro dépendance vers le reste de Marius.

## Sous-modules

| Fichier | Rôle |
|---------|------|
| `contracts.py` | `ProviderEntry`, `AuthType`, `ProviderKind` |
| `registry.py` | `PROVIDER_REGISTRY`, `ProviderDefinition`, `ProviderProtocol`, `ContextWindowStrategy` |
| `store.py` | Lecture/écriture de `~/.marius/marius_providers.json` |
| `fetcher.py` | Récupération des modèles disponibles via HTTP |
| `auth_flow.py` | Flow OAuth PKCE pour ChatGPT/OpenAI |
| `wizard.py` | Wizards CLI interactifs (add, edit, set model) |

---

## contracts

```python
class AuthType(str, Enum):
    AUTH   # OAuth / navigateur
    API    # URL + clé API

class ProviderKind(str, Enum):
    OPENAI / OLLAMA

@dataclass
class ProviderEntry:
    id: str              # UUID court (8 chars)
    name: str            # nom donné par l'utilisateur
    provider: str        # ProviderKind ou str pour les futurs providers
    auth_type: str
    base_url: str
    api_key: str
    model: str
    added_at: str        # ISO 8601
    metadata: dict       # refresh_token, expires, etc.

    @classmethod
    def generate_id(cls) -> str
```

---

## registry

```python
class ProviderProtocol(str, Enum):
    OPENAI_COMPATIBLE   # POST /chat/completions
    OLLAMA_NATIVE       # POST /api/chat

class ContextWindowStrategy(str, Enum):
    STATIC / API / WEB_SEARCH / FALLBACK

@dataclass(frozen=True)
class ProviderDefinition:
    kind, label, default_base_url, requires_api_key
    models_endpoint, models_list_key, model_name_key
    supported_auth_types: tuple[str, ...]
    protocol: ProviderProtocol
    chat_endpoint: str
    context_window_strategy: ContextWindowStrategy
    context_window_api_endpoint: str
    model_id_prefix_filter: tuple[str, ...]

PROVIDER_REGISTRY: dict[str, ProviderDefinition]
```

**Ajouter un provider** = une entrée dans `PROVIDER_REGISTRY`. Un nouveau fichier Python n'est nécessaire que si le protocole HTTP est nouveau.

---

## store

```python
class ProviderStore:
    def __init__(self, path: Path = ~/.marius/marius_providers.json)
    def load(self)  -> list[ProviderEntry]
    def save(self, entries: list[ProviderEntry]) -> None
    def add(self, entry: ProviderEntry) -> None
    def update(self, entry: ProviderEntry) -> bool   # True si trouvé par id
```

Format du fichier — tableau JSON, un objet par provider :

```json
[
  {
    "id": "abc123",
    "name": "mon-openai",
    "provider": "openai",
    "auth_type": "api",
    "base_url": "https://api.openai.com/v1",
    "api_key": "sk-...",
    "model": "gpt-4o",
    "added_at": "2026-05-08T10:00:00+00:00",
    "metadata": {}
  }
]
```

---

## fetcher

```python
class ModelFetchError(RuntimeError): ...

def fetch_models(entry: ProviderEntry, *, timeout: int = 10) -> list[str]
    # Pour OpenAI (auth_type=api) : GET /models avec Bearer token
    # Pour OpenAI (auth_type=auth) : lit ~/.codex/models_cache.json
    # Pour Ollama : GET /api/tags

def fetch_chatgpt_oauth_models(cache_path: Path = ~/.codex/models_cache.json) -> list[str]
    # Lit le cache Codex CLI, trié par priorité. Fallback statique si absent.
```

---

## auth_flow

Flow OAuth PKCE pour ChatGPT — stdlib uniquement.

```python
@dataclass
class OAuthTokenResult:
    access_token: str
    refresh_token: str
    expires: float
    obtained_at: str

class OAuthError(RuntimeError): ...

class ChatGPTOAuthFlow:
    def __init__(self, *, redirect_uri, callback_host, callback_port, timeout_seconds, token_transport)
    def run(self, *, on_url=None) -> OAuthTokenResult

def generate_pkce()         -> tuple[str, str]   # (verifier, challenge S256)
def build_authorize_url(*, code_challenge, state, redirect_uri) -> str
def exchange_code(code, verifier, redirect_uri, *, transport=None) -> dict
def refresh_token(token, *, transport=None) -> dict
```

**Séquence OAuth** :
1. Génère PKCE (verifier + challenge SHA256)
2. Ouvre le navigateur sur l'URL d'autorisation OpenAI
3. Démarre un serveur HTTP local sur le port 1455
4. Attend le callback `GET /auth/callback?code=...&state=...`
5. Échange le code contre un token
6. Retourne `OAuthTokenResult`

---

## wizard

```python
def run_add_provider(store=None, console=None) -> None
    # 5 étapes : auth type → provider → config → modèles → nom

def run_edit_provider(store=None, console=None) -> None
    # Sélection → champs éditables (Entrée = conserver) → re-fetch modèles

def run_set_model(store=None, console=None) -> str | None
    # Sélection provider (auto si un seul) → liste modèles → sauvegarde
    # Retourne le nom du modèle choisi — utilisable depuis /model dans le REPL
```

---

## Invariants

- `ProviderStore` crée le dossier `~/.marius/` s'il n'existe pas.
- Les clés API sont stockées en clair dans le JSON — chiffrement non implémenté.
- Le token OAuth est stocké dans `ProviderEntry.api_key` ; `refresh_token` et `expires` dans `metadata`.
- `fetch_models` pour OpenAI OAuth lit `~/.codex/models_cache.json` (populé par le Codex CLI) avec fallback statique.
- `run_set_model` retourne `None` si annulé, le nom du modèle sinon — le REPL peut réagir en conséquence.
