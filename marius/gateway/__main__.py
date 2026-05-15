"""Point d'entrée subprocess du gateway.

Lancé par : python -m marius.gateway --agent <nom>
"""

from __future__ import annotations

import argparse
import sys


def main() -> None:
    parser = argparse.ArgumentParser(prog="marius.gateway")
    parser.add_argument("--agent", required=True, metavar="NOM")
    args = parser.parse_args()

    from marius.config.store import ConfigStore
    from marius.provider_config.store import ProviderStore

    config_store = ConfigStore()
    config = config_store.load()
    if config is None:
        sys.stderr.write("Gateway : config introuvable.\n")
        sys.exit(1)

    agent_cfg = config.get_agent(args.agent)
    if agent_cfg is None:
        sys.stderr.write(f"Gateway : agent '{args.agent}' introuvable.\n")
        sys.exit(1)

    provider_store = ProviderStore()
    providers = provider_store.load()
    entry = next((p for p in providers if p.id == agent_cfg.provider_id), None)
    if entry is None and providers:
        entry = providers[0]
    if entry is None:
        sys.stderr.write("Gateway : aucun provider configuré.\n")
        sys.exit(1)

    if agent_cfg.model and agent_cfg.model != entry.model:
        from dataclasses import replace
        entry = replace(entry, model=agent_cfg.model)

    from marius.gateway.server import GatewayServer
    server = GatewayServer(
        agent_name=args.agent,
        entry=entry,
        agent_config=agent_cfg,
        permission_mode=agent_cfg.permission_mode,
    )
    server.serve()


if __name__ == "__main__":
    main()
