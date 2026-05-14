"""Point d'entrée : python -m marius.channels.dashboard [--port N] [--static-dir PATH]"""

from __future__ import annotations

import argparse
import sys
import webbrowser
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(prog="marius.channels.dashboard")
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--static-dir", default=None, metavar="PATH")
    parser.add_argument("--no-open", action="store_true")
    args = parser.parse_args()

    if args.static_dir:
        static_dir = Path(args.static_dir)
    else:
        # repo root front/ (editable install)
        candidate = Path(__file__).parent.parent.parent.parent / "front"
        if candidate.exists():
            static_dir = candidate
        else:
            # installed package: look for bundled static/
            static_dir = Path(__file__).parent / "static"

    if not static_dir.exists():
        sys.stderr.write(f"Dashboard: static dir not found: {static_dir}\n")
        sys.stderr.write("Hint: run from the marius project root, or pass --static-dir\n")
        sys.exit(1)

    from marius.channels.dashboard.server import DashboardServer
    server = DashboardServer(static_dir=static_dir, port=args.port, host=args.host)

    if not args.no_open:
        import threading
        threading.Timer(0.5, lambda: webbrowser.open(f"http://{args.host}:{args.port}")).start()

    server.serve()


if __name__ == "__main__":
    main()
