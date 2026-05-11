# guardian_policy

## Rôle

Décide si une extension de la zone allow est autorisée, refusée ou soumise à confirmation. Brique de sécurité pure et synchrone — ne modifie aucun état, ne demande rien à l'utilisateur.

## Couche

Kernel

## Standalone

Oui. S'insère entre n'importe quel agent et une action sensible.

## Dépendances

- `marius.kernel.project_context` — `PermissionMode`

## Interface publique

```python
class AllowExpansionStatus(str, Enum):
    NOT_REQUIRED  # déjà autorisé ou aucune zone allow déclarée
    ALLOW         # extension accordée
    DENY          # extension refusée
    ASK           # demander confirmation à l'utilisateur

class AllowExpansionCode(str, Enum):
    ALREADY_ALLOWED
    POWER_MODE_NO_MUTATION
    SAFE_MODE_FORBIDS_EXPANSION
    NO_ALLOW_ZONE_DECLARED
    EXPLICIT_USER_REQUEST_REQUIRED
    REQUESTED_ROOT_TOO_BROAD
    REQUESTED_ROOT_ALLOWED

@dataclass(frozen=True)
class AllowExpansionRequest:
    permission_mode: PermissionMode
    workspace_root: Path | None
    current_allowed_roots: tuple[Path, ...]
    requested_root: Path
    reason: AllowExpansionReason
    explicit_user_request: bool = False

@dataclass(frozen=True)
class AllowExpansionDecision:
    status: AllowExpansionStatus
    code: AllowExpansionCode
    roots_to_add: tuple[Path, ...]   # rempli uniquement si status == ALLOW
    metadata: dict

class GuardianPolicy(Protocol):
    def review_allow_expansion(self, request: AllowExpansionRequest) -> AllowExpansionDecision: ...

class DefaultGuardianPolicy:
    """Implémentation par défaut — injectable dans project_context."""
```

## Arbre de décision (DefaultGuardianPolicy)

```
requested_root déjà dans allowed_roots ?
  → NOT_REQUIRED / ALREADY_ALLOWED

mode == POWER ?
  → NOT_REQUIRED / POWER_MODE_NO_MUTATION  (usage sans mutation)

mode == SAFE ?
  → DENY / SAFE_MODE_FORBIDS_EXPANSION

aucune zone allow déclarée (ni roots ni workspace) ?
  → NOT_REQUIRED / NO_ALLOW_ZONE_DECLARED

explicit_user_request == False ?
  → ASK / EXPLICIT_USER_REQUEST_REQUIRED

requested_root trop large (parent d'une root existante) ?
  → DENY / REQUESTED_ROOT_TOO_BROAD

→ ALLOW / REQUESTED_ROOT_ALLOWED
```

## Invariants

- Aucune mutation d'état — retourne uniquement une décision.
- `roots_to_add` est vide sauf quand `status == ALLOW`.
- Le mode `power` n'autorise pas l'auto-extension de l'allow-list.
- Une root "trop large" est une root qui serait parent d'une root déjà autorisée ou du workspace.
