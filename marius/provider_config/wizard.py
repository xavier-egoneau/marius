"""Wizard CLI pour configurer les providers Marius.

Utilise `rich` pour les couleurs. Standalone : aucune dépendance vers le
reste de Marius.
"""

from __future__ import annotations

from getpass import getpass

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from .auth_flow import ChatGPTOAuthFlow, OAuthError
from .contracts import AuthType, ProviderEntry, ProviderKind
from .fetcher import ModelFetchError, fetch_models
from .registry import PROVIDER_REGISTRY, ProviderDefinition
from .store import ProviderStore


_AUTH_CHOICES: list[tuple[str, str]] = [
    (AuthType.AUTH, "Connexion OAuth / navigateur"),
    (AuthType.API, "URL + clé API"),
]


# ── helpers ──────────────────────────────────────────────────────────────────


def _header(console: Console, title: str) -> None:
    console.print()
    console.print(Panel(f"[bold white]{title}[/]", style="bold cyan", expand=False))
    console.print()


def _step(console: Console, n: int, total: int, title: str) -> None:
    console.print(f"\n[bold cyan]{n} / {total}[/]  [white]{title}[/]\n")


def _pick(console: Console, choices: list[tuple[str, str]], prompt: str = "Votre choix") -> int:
    """Affiche une liste numérotée et retourne l'index (0-based) du choix."""
    for i, (label, desc) in enumerate(choices, 1):
        console.print(f"  [bold green]{i}[/]  [white]{label:<14}[/] [dim]{desc}[/]")
    console.print()
    while True:
        raw = Prompt.ask(
            f"[yellow]› {prompt}[/] [dim][1-{len(choices)}][/dim]",
            console=console,
        )
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(choices):
                return idx
        except (ValueError, TypeError):
            pass
        console.print(f"  [red]Entrez un nombre entre 1 et {len(choices)}.[/]\n")


def _ask_api_key(console: Console) -> str:
    """Demande une clé API masquée."""
    console.print()
    try:
        return getpass("  › Clé API : ")
    except Exception:
        return Prompt.ask("[yellow]› Clé API[/]", console=console, password=True)


def _masked(key: str, visible: int = 4) -> str:
    if not key:
        return "(vide)"
    return key[:visible] + "****" if len(key) > visible else "****"


def _providers_for_auth(auth_type: str) -> list[tuple[str, ProviderDefinition]]:
    return [
        (kind, defn)
        for kind, defn in PROVIDER_REGISTRY.items()
        if auth_type in defn.supported_auth_types
    ]


def _fetch_with_spinner(console: Console, entry: ProviderEntry) -> list[str]:
    with console.status("[cyan]Connexion en cours...[/]", spinner="dots"):
        try:
            models = fetch_models(entry)
        except ModelFetchError as exc:
            console.print(f"\n  [yellow]⚠  Récupération des modèles impossible : {exc}[/]")
            return []
    console.print(f"  [bold green]✓[/]  {len(models)} modèle(s) trouvé(s)\n")
    return models


def _choose_model(console: Console, models: list[str], current: str = "") -> str:
    if not models:
        hint = f" [dim][{current}][/dim]" if current else ""
        return Prompt.ask(f"[yellow]› Modèle{hint}[/]", console=console, default=current)
    choices = [(m, "") for m in models]
    idx = _pick(console, choices, prompt="Modèle")
    return models[idx]


# ── oauth ─────────────────────────────────────────────────────────────────────


def _run_oauth(
    console: Console,
    provider_kind: str,
    defn: ProviderDefinition,
) -> tuple[str, str, dict[str, object]]:
    """Lance le flow OAuth pour le provider donné.

    Retourne (base_url, access_token, metadata) ou ("", "", {}) en cas d'échec.
    """
    if provider_kind != ProviderKind.OPENAI:
        console.print(f"\n  [red]OAuth non supporté pour « {provider_kind} ».[/]\n")
        return "", "", {}

    console.print("  [dim]Un navigateur va s'ouvrir pour vous connecter à ChatGPT.[/]")
    console.print("  [dim]En attente du callback sur http://localhost:1455/auth/callback...[/]\n")

    def on_url(url: str) -> None:
        import webbrowser
        console.print(f"  [cyan]URL d'autorisation :[/] [dim]{url[:80]}...[/]")
        webbrowser.open(url)

    try:
        with console.status("[cyan]En attente de la confirmation dans le navigateur...[/]", spinner="dots"):
            result = ChatGPTOAuthFlow().run(on_url=on_url)
    except OAuthError as exc:
        console.print(f"\n  [red]Échec de l'authentification : {exc}[/]\n")
        return "", "", {}

    console.print(f"  [bold green]✓[/]  Connexion réussie\n")
    metadata: dict[str, object] = {
        "auth_method": "oauth_pkce",
        "refresh_token": result.refresh_token,
        "expires": result.expires,
        "obtained_at": result.obtained_at,
    }
    return defn.default_base_url, result.access_token, metadata


# ── wizards ──────────────────────────────────────────────────────────────────


def run_add_provider(
    store: ProviderStore | None = None,
    console: Console | None = None,
) -> None:
    """Lance le wizard d'ajout d'un provider."""
    console = console or Console()
    store = store or ProviderStore()
    total = 5

    _header(console, "Marius — Ajout d'un provider")

    # 1 / 5 — type d'auth
    _step(console, 1, total, "Type d'authentification")
    auth_idx = _pick(console, _AUTH_CHOICES)
    auth_type = _AUTH_CHOICES[auth_idx][0]

    # 2 / 5 — provider
    _step(console, 2, total, "Provider")
    available = _providers_for_auth(auth_type)
    if not available:
        console.print("\n  [red]Aucun provider disponible pour ce type d'auth.[/]\n")
        return

    provider_choices = [(kind, defn.label) for kind, defn in available]
    provider_idx = _pick(console, provider_choices)
    chosen_kind, chosen_defn = available[provider_idx]

    # 3 / 5 — configuration
    _step(console, 3, total, f"Configuration — {chosen_defn.label}")

    base_url = chosen_defn.default_base_url
    api_key = ""
    metadata: dict[str, object] = {}

    if auth_type == AuthType.AUTH:
        base_url, api_key, metadata = _run_oauth(console, chosen_kind, chosen_defn)
        if not api_key:
            return
    else:
        console.print(f"  [dim]URL par défaut : {chosen_defn.default_base_url}[/]\n")
        base_url = Prompt.ask(
            f"[yellow]› URL de base[/] [dim][{chosen_defn.default_base_url}][/dim]",
            console=console,
            default=chosen_defn.default_base_url,
        )
        if chosen_defn.requires_api_key:
            api_key = _ask_api_key(console)

    # 4 / 5 — connexion et modèles
    _step(console, 4, total, "Connexion et modèles disponibles")
    draft = ProviderEntry(
        id=ProviderEntry.generate_id(),
        name="",
        provider=chosen_kind,
        auth_type=auth_type,
        base_url=base_url,
        api_key=api_key,
    )
    models = _fetch_with_spinner(console, draft)
    model = _choose_model(console, models)

    # 5 / 5 — finalisation
    _step(console, 5, total, "Finalisation")
    existing = store.load()
    default_name = f"{chosen_kind}-{len(existing) + 1}"
    name = Prompt.ask(
        f"[yellow]› Nom du provider[/] [dim][{default_name}][/dim]",
        console=console,
        default=default_name,
    )

    entry = ProviderEntry(
        id=draft.id,
        name=name,
        provider=chosen_kind,
        auth_type=auth_type,
        base_url=base_url,
        api_key=api_key,
        model=model,
        metadata=metadata,
    )
    store.add(entry)
    console.print(
        f"\n  [bold green]✓[/]  Provider [bold]{name}[/] ajouté dans "
        f"[dim]{store.path}[/dim]\n"
    )


def run_edit_provider(
    store: ProviderStore | None = None,
    console: Console | None = None,
) -> None:
    """Lance le wizard d'édition d'un provider existant."""
    console = console or Console()
    store = store or ProviderStore()

    _header(console, "Marius — Édition d'un provider")

    entries = store.load()
    if not entries:
        console.print(
            "  [yellow]Aucun provider configuré. "
            "Utilisez [bold]marius add provider[/bold] d'abord.[/]\n"
        )
        return

    console.print("[bold cyan]Providers configurés[/]\n")
    provider_choices = [(e.name, f"{e.provider} / {e.model or '—'}") for e in entries]
    idx = _pick(console, provider_choices, prompt="Provider à éditer")
    entry = entries[idx]
    defn = PROVIDER_REGISTRY.get(entry.provider)

    console.print(
        f"\n[bold cyan]Édition de « {entry.name} »[/]  "
        "[dim](Entrée = conserver la valeur actuelle)[/dim]\n"
    )

    name = Prompt.ask(
        f"[yellow]› Nom[/] [dim][{entry.name}][/dim]",
        console=console,
        default=entry.name,
    )
    base_url = Prompt.ask(
        f"[yellow]› URL de base[/] [dim][{entry.base_url}][/dim]",
        console=console,
        default=entry.base_url,
    )

    api_key = entry.api_key
    if defn and defn.requires_api_key:
        masked = _masked(entry.api_key)
        console.print(f"\n  [dim]Clé actuelle : {masked}[/]")
        change = Prompt.ask(
            "[yellow]› Modifier la clé API ?[/] [dim][o/N][/dim]",
            console=console,
            default="N",
        )
        if change.strip().lower() in ("o", "oui", "y", "yes"):
            api_key = _ask_api_key(console)

    console.print()
    draft = ProviderEntry(
        id=entry.id,
        name=name,
        provider=entry.provider,
        auth_type=entry.auth_type,
        base_url=base_url,
        api_key=api_key,
        model=entry.model,
    )
    models = _fetch_with_spinner(console, draft)
    model = _choose_model(console, models, current=entry.model)

    updated = ProviderEntry(
        id=entry.id,
        name=name,
        provider=entry.provider,
        auth_type=entry.auth_type,
        base_url=base_url,
        api_key=api_key,
        model=model,
        added_at=entry.added_at,
        metadata=entry.metadata,
    )
    store.update(updated)
    console.print(
        f"\n  [bold green]✓[/]  Provider [bold]{name}[/] mis à jour dans "
        f"[dim]{store.path}[/dim]\n"
    )


def run_set_model(
    store: ProviderStore | None = None,
    console: Console | None = None,
) -> str | None:
    """Change le modèle actif d'un provider configuré.

    Retourne le nom du modèle sélectionné, ou None si annulé.
    Utilisable depuis les canaux pour implémenter /model.
    """
    console = console or Console()
    store = store or ProviderStore()

    _header(console, "Marius — Choix du modèle")

    entries = store.load()
    if not entries:
        console.print(
            "  [yellow]Aucun provider configuré. "
            "Utilisez [bold]marius add provider[/bold] d'abord.[/]\n"
        )
        return None

    if len(entries) == 1:
        entry = entries[0]
        console.print(f"  [dim]Provider : {entry.name} ({entry.provider})[/]\n")
    else:
        console.print("[bold cyan]Providers disponibles[/]\n")
        choices = [(e.name, f"{e.provider} / {e.model or '—'}") for e in entries]
        idx = _pick(console, choices, prompt="Provider")
        entry = entries[idx]

    console.print()
    models = _fetch_with_spinner(console, entry)
    model = _choose_model(console, models, current=entry.model)

    if model == entry.model:
        console.print(f"\n  [dim]Modèle inchangé : {model}[/]\n")
        return model

    updated = ProviderEntry(
        id=entry.id,
        name=entry.name,
        provider=entry.provider,
        auth_type=entry.auth_type,
        base_url=entry.base_url,
        api_key=entry.api_key,
        model=model,
        added_at=entry.added_at,
        metadata=entry.metadata,
    )
    store.update(updated)
    console.print(
        f"\n  [bold green]✓[/]  Modèle [bold]{model}[/] activé "
        f"pour [bold]{entry.name}[/]\n"
    )
    return model
