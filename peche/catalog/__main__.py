"""CLI : python3 -m peche.catalog harvest [--skip-remote]."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="peche.catalog")
    sub = parser.add_subparsers(dest="cmd", required=True)
    harvest_p = sub.add_parser("harvest", help="Récolter GetCapabilities / ArcGIS")
    harvest_p.add_argument(
        "--skip-remote",
        action="store_true",
        help="Ne pas appeler les services ; catalogue curated seulement",
    )
    sub.add_parser(
        "warm-caps",
        help="Pré-charger GetCapabilities pour la découverte de couches",
    )
    args = parser.parse_args(argv)

    if args.cmd == "harvest":
        from peche.catalog.harvest import harvest

        harvest(skip_remote=args.skip_remote)
        return 0
    if args.cmd == "warm-caps":
        from peche.catalog.discover import warm_capabilities_cache

        n = warm_capabilities_cache()
        print(f"GetCapabilities pré-chargés pour {n} service(s).")
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
