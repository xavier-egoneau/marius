# project_context

## Rôle

Résout explicitement le projet actif, les projets cités et le scope de session (`canonical` / `project` / `branch`). Produit le préambule et les sources pour `context_builder` sans assembler lui-même le Markdown.

## Couche

Kernel

## Standalone

Oui. La même convention peut être reprise par tout système multi-projets.

## Dépendances

- `marius.kernel.context_builder` — `ContextSource`, `ContextBuildInput`
- `marius.kernel.guardian_policy` — `GuardianPolicy` (injectable)

## Interface publique

```python
class PermissionMode(str, Enum):
    SAFE    # projet actif doit rester dans la zone allow
    LIMITED # promotion explicite d'un projet hors workspace autorisée
    POWER   # projet hors workspace accepté sans promotion préalable

class SessionScope(str, Enum):
    CANONICAL / PROJECT / BRANCH

@dataclass
class ProjectContextInput:
    mode: str                       # "local" | "global"
    session_scope: SessionScope
    permission_mode: PermissionMode
    active_project: str | None      # chemin absolu du projet actif
    cited_projects: list[str]
    workspace_root: str | None
    allowed_roots: list[str]
    activate_requested_project: bool = False
    branch: str | None = None

@dataclass
class ResolvedProjectContext:
    preamble: str
    context_build_input: ContextBuildInput
    active_project_root: str | None
    allowed_roots_effective: list[str]
    allow_expansion_status: str     # "not_required" | "allow" | "deny" | "ask"
    allow_expansion_code: str
    allow_expansion_roots: list[str]
    metadata: dict
```

## Modes de permission

| Mode | Comportement |
|------|-------------|
| `safe` | Le projet actif doit être dans la zone allow — refuse toute extension |
| `limited` | Autorise la promotion d'un projet hors workspace si l'utilisateur le demande explicitement |
| `power` | Accepte un projet hors workspace sans promotion — la zone allow n'est pas mutée |

## Invariants

- En scope `project`, un projet actif est obligatoire.
- En scope `branch`, un identifiant de branche est obligatoire.
- En mode `global`, l'absence de projet actif est autorisée tant qu'aucun projet n'est fixé.
- Les projets cités restent des références visibles dans le préambule — ils n'étendent pas les permissions.
- La politique d'extension de zone allow est déléguée à `guardian_policy` — `project_context` ne réimplémente pas la règle.
