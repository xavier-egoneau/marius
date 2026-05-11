# Marius — Guardian policy minimale pour l’extension d’allow

## But

Extraire hors de `project_context` la décision d’extension de la zone allow afin que `project_context` reste un résolveur de contexte, pas un moteur de politique de sécurité.

## Nom recommandé

Préférer **`guardian_policy`** pour cette slice.

Pourquoi :
- `guardian` est un nom plus large et peut ensuite porter d’autres contrôles ;
- `guardian_policy` décrit ici une brique **pure, synchrone, testable**, sans rendu ni I/O ;
- on garde la possibilité qu’un futur `security_guard` orchestre plusieurs politiques, dont celle-ci.

---

## Frontière visée

### `project_context` garde
- la résolution du projet actif ;
- la validation `local` / `global` / `branch` ;
- la normalisation des paths ;
- la construction du préambule et des `ContextSource` ;
- l’application mécanique d’une décision déjà prise.

### `guardian_policy` prend
- la décision d’**étendre ou non** la zone allow ;
- les statuts `allow` / `deny` / `ask` ;
- la règle de largeur acceptable d’une promotion ;
- la condition d’explicitation utilisateur pour une promotion hors zone allow.

### `host` / `render` gardent
- la formulation utilisateur de la demande de confirmation ;
- le stockage éventuel d’une approbation ;
- l’UI concrète.

---

## API minimale proposée

```python
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Protocol

from marius.kernel.project_context import PermissionMode


class AllowExpansionReason(str, Enum):
    ACTIVATE_PROJECT = "activate_project"


class AllowExpansionStatus(str, Enum):
    NOT_REQUIRED = "not_required"
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"


class AllowExpansionCode(str, Enum):
    ALREADY_ALLOWED = "already_allowed"
    POWER_MODE_NO_MUTATION = "power_mode_no_mutation"
    SAFE_MODE_FORBIDS_EXPANSION = "safe_mode_forbids_expansion"
    EXPLICIT_USER_REQUEST_REQUIRED = "explicit_user_request_required"
    REQUESTED_ROOT_TOO_BROAD = "requested_root_too_broad"
    REQUESTED_ROOT_ALLOWED = "requested_root_allowed"


@dataclass(slots=True, frozen=True)
class AllowExpansionRequest:
    permission_mode: PermissionMode
    workspace_root: Path | None
    current_allowed_roots: tuple[Path, ...]
    requested_root: Path
    reason: AllowExpansionReason
    explicit_user_request: bool = False


@dataclass(slots=True, frozen=True)
class AllowExpansionDecision:
    status: AllowExpansionStatus
    code: AllowExpansionCode
    roots_to_add: tuple[Path, ...] = ()
    metadata: dict[str, object] = field(default_factory=dict)


class GuardianPolicy(Protocol):
    def review_allow_expansion(
        self,
        request: AllowExpansionRequest,
    ) -> AllowExpansionDecision:
        ...
```

---

## Pourquoi cette API est la plus petite utile

Elle ne transporte que :
- le mode de permission ;
- la zone allow actuelle ;
- la root candidate ;
- le motif de la demande ;
- le signal d’explicitation utilisateur.

Elle ne transporte pas :
- le catalogue projet ;
- les documents Markdown ;
- le scope de session ;
- du texte de rendu ;
- des objets host/UI.

Donc :
- **standalone** ;
- **testable en mémoire** ;
- **sans couplage** à `context_builder`, `render` ou `storage`.

---

## Contrat sémantique

### `NOT_REQUIRED`
Aucune mutation n’est nécessaire.

Cas typiques :
- la root demandée est déjà couverte par la zone allow ;
- le mode `power` accepte le projet actif hors zone allow sans promotion.

Dans ce cas, `roots_to_add` **doit être vide**.

### `ALLOW`
La politique autorise explicitement l’extension.

Dans ce cas :
- `roots_to_add` contient la ou les roots exactes à ajouter ;
- pour cette slice, la valeur attendue est en pratique **une seule root** : `requested_root`.

### `DENY`
La politique refuse l’extension.

Exemples :
- mode `safe` ;
- root jugée trop large ;
- autre blocage de politique.

Dans ce cas, `roots_to_add` **doit être vide**.

### `ASK`
Une confirmation ou une demande explicite utilisateur manque.

Exemple minimal :
- mode `limited` + root hors zone allow + pas de demande explicite.

Dans ce cas, `roots_to_add` **doit être vide**.

---

## Invariants

1. **`project_context` ne décide jamais lui-même si une extension est acceptable.**
   Il constate seulement qu’une extension serait nécessaire, puis délègue.

2. **Aucune mutation de l’allow-list sans décision `ALLOW`.**

3. **`project_context` n’ajoute que `decision.roots_to_add`.**
   Il ne reconstruit pas la politique à partir des entrées.

4. **`roots_to_add` est vide sauf si `status == ALLOW`.**

5. **La politique ne connaît ni documents projet ni UI.**

6. **La politique manipule des paths normalisés.**
   La normalisation reste de préférence côté `project_context` pour garder un seul point canonique.

7. **Une promotion ne peut jamais élargir implicitement à autre chose que la root explicitement accordée.**
   Pas de promotion silencieuse au parent, au workspace entier, ou à une liste dérivée.

8. **Les projets cités n’influencent jamais la politique d’allow.**

9. **Le mode `power` ne doit pas provoquer une mutation inutile.**
   Il autorise l’usage, pas l’extension automatique de l’allow-list.

10. **La largeur acceptable d’une root est une règle du gardien, pas du résolveur de contexte.**

---

## Règles minimales de politique

Pour cette première slice, la politique peut rester volontairement petite :

1. Si `requested_root` est déjà couverte par `current_allowed_roots` → `NOT_REQUIRED / ALREADY_ALLOWED`.
2. Si `permission_mode == POWER` → `NOT_REQUIRED / POWER_MODE_NO_MUTATION`.
3. Si `permission_mode == SAFE` et qu’une extension serait nécessaire → `DENY / SAFE_MODE_FORBIDS_EXPANSION`.
4. Si `permission_mode == LIMITED` et `explicit_user_request is False` → `ASK / EXPLICIT_USER_REQUEST_REQUIRED`.
5. Si `permission_mode == LIMITED` et la root demandée est jugée trop large → `DENY / REQUESTED_ROOT_TOO_BROAD`.
6. Sinon → `ALLOW / REQUESTED_ROOT_ALLOWED` avec `roots_to_add=(requested_root,)`.

La règle “trop large” peut rester minimale et testable, par exemple :
- refuser une root candidate qui est un parent d’une root déjà allowée ;
- refuser une root candidate égale au `workspace_root` quand la demande vise un projet précis ;
- refuser une root candidate manifestement plus haute que le projet demandé si cette information est déjà encodée côté appelant.

Si on veut rester strictement minimal, la première version peut se limiter au premier point :
- **refuser toute root candidate qui contient déjà une root allowée plus spécifique**.

---

## Usage par `project_context`

Séquence recommandée :

1. `project_context` valide les invariants de session.
2. `project_context` normalise `workspace_root`, `allowed_roots`, `active_project.root_path`.
3. `project_context` calcule la base allow courante.
4. Si aucun projet actif → pas d’appel à la politique.
5. Si le projet actif est déjà couvert → pas de mutation ; éventuellement pas d’appel, ou appel toléré qui renvoie `NOT_REQUIRED`.
6. Si une extension serait nécessaire, `project_context` appelle `guardian_policy.review_allow_expansion(...)`.
7. `project_context` applique la décision sans réinterpréter la politique :
   - `ALLOW` → merge de `roots_to_add` dans `allowed_roots` ;
   - `NOT_REQUIRED` → aucun ajout ;
   - `ASK` ou `DENY` → erreur métier stable avec la décision attachée.

Pseudo-code :

```python
def _resolve_allowed_roots(...):
    if active_project is None:
        return allowed_roots, None

    decision = guardian_policy.review_allow_expansion(
        AllowExpansionRequest(
            permission_mode=context_input.permission_mode,
            workspace_root=context_input.workspace_root,
            current_allowed_roots=tuple(allowed_roots),
            requested_root=active_project.root_path,
            reason=AllowExpansionReason.ACTIVATE_PROJECT,
            explicit_user_request=context_input.activate_requested_project,
        )
    )

    if decision.status is AllowExpansionStatus.ALLOW:
        return merge(allowed_roots, decision.roots_to_add), decision

    if decision.status is AllowExpansionStatus.NOT_REQUIRED:
        return allowed_roots, decision

    raise ProjectResolutionError.from_guardian_decision(decision)
```

---

## Retour attendu de `project_context`

`ResolvedProjectContext` peut rester presque inchangé, avec seulement des métadonnées enrichies :

```python
metadata = {
    "allow_expansion_status": decision.status.value,
    "allow_expansion_code": decision.code.value,
    "allow_expansion_roots": [str(root) for root in decision.roots_to_add],
}
```

Suggestion : déprécier ensuite `active_project_promoted: bool` au profit de champs plus stables et plus génériques :
- `allow_expansion_status`
- `allow_expansion_code`
- `allow_expansion_roots`

Si on veut garder la compatibilité courte :
- `active_project_promoted = decision.status == AllowExpansionStatus.ALLOW`

---

## Tests TDD minimaux

### Tests de la politique seule

1. `already_allowed_returns_not_required`
2. `power_mode_returns_not_required_without_mutation`
3. `safe_mode_denies_expansion`
4. `limited_mode_without_explicit_request_returns_ask`
5. `limited_mode_with_explicit_request_allows_requested_root`
6. `limited_mode_denies_root_too_broad`

### Tests d’intégration `project_context` + politique

1. `project_context_does_not_mutate_allow_without_allow_decision`
2. `project_context_merges_exact_roots_returned_by_policy`
3. `project_context_raises_stable_error_on_ask_decision`
4. `project_context_raises_stable_error_on_deny_decision`
5. `project_context_preserves_power_mode_without_promotion`

Double minimal pour tests d’intégration :

```python
class StubGuardianPolicy:
    def __init__(self, decision: AllowExpansionDecision) -> None:
        self.decision = decision
        self.calls = []

    def review_allow_expansion(self, request: AllowExpansionRequest) -> AllowExpansionDecision:
        self.calls.append(request)
        return self.decision
```

---

## Noms de types recommandés

### Recommandation principale
- module : `guardian_policy.py`
- protocole : `GuardianPolicy`
- entrée : `AllowExpansionRequest`
- sortie : `AllowExpansionDecision`
- statut : `AllowExpansionStatus`
- code stable : `AllowExpansionCode`
- raison : `AllowExpansionReason`

### Noms à éviter
- `GuardianResult` : trop vague
- `ProjectPermissionDecision` : mélange projet et sécurité
- `AllowMutationContext` : centré implémentation plutôt que métier
- `PromotionDecision` : trop lié au cas “active project” actuel

---

## Décision pratique recommandée

Pour la slice immédiate :
- **introduire `guardian_policy` comme protocole + types purs** ;
- **injecter cette dépendance dans `ProjectContextResolver`** ;
- **retirer de `project_context` la logique `limited/safe` de promotion** ;
- **conserver `power` comme absence de mutation, pas comme auto-extension** ;
- **faire vivre les messages utilisateur hors de cette brique**.

C’est la plus petite API qui :
- garde les frontières nettes ;
- empêche que `project_context` reprenne la politique ;
- reste simple à tester en TDD ;
- prépare un futur gardien plus large sans jeter cette slice.
