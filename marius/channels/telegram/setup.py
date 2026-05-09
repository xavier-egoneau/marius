"""Wizard de configuration du canal Telegram."""

from __future__ import annotations

from rich.console import Console

from .api import get_me
from .config import TelegramChannelConfig, save


def run_telegram_setup(console: Console | None = None) -> TelegramChannelConfig | None:
    """Lance le wizard interactif. Retourne la config sauvegardée ou None."""
    c = console or Console(highlight=False)

    c.print()
    c.print("[bold color(208)]Configuration Telegram[/]\n")
    c.print("  1. Va sur Telegram → @BotFather → /newbot")
    c.print("  2. Copie le token fourni (format  123456:ABCdef...)\n")

    token = c.input("  Token du bot : ").strip()
    if not token:
        c.print("  [dim]Annulé.[/]\n")
        return None

    c.print("\n  [dim]Vérification du token…[/]")
    me = get_me(token)
    if not me:
        c.print("\n  [bold color(208)]Token invalide ou bot injoignable.[/]\n")
        return None

    bot_name = me.get("username", "?")
    c.print(f"  [dim]Bot vérifié : @{bot_name}[/]\n")

    c.print("  IDs Telegram autorisés (ton user_id, séparés par des virgules).")
    c.print("  [dim]Envoie /start à @userinfobot pour connaître ton ID.[/]")
    c.print("  [dim]Entrée vide = tout le monde peut écrire au bot (déconseillé).[/]\n")
    raw_users = c.input("  IDs autorisés : ").strip()
    allowed_users: list[int] = []
    if raw_users:
        for u in raw_users.split(","):
            u = u.strip()
            if u.lstrip("-").isdigit():
                allowed_users.append(int(u))

    from marius.config.store import ConfigStore
    config = ConfigStore().load()
    agent_default = config.main_agent if config else "main"
    agent_name = c.input(f"  Agent associé [[dim]{agent_default}[/]]: ").strip() or agent_default

    cfg = TelegramChannelConfig(
        token=token,
        agent_name=agent_name,
        allowed_users=allowed_users,
    )
    save(cfg)

    c.print(f"\n  [dim]✓ Config sauvegardée — bot @{bot_name} → agent {agent_name}[/]")
    c.print("  [dim]Le bot démarrera automatiquement avec le gateway.[/]\n")
    return cfg
