"""CLI spatial : python3 -m peche.spatial link|zones-peche"""

from __future__ import annotations

import argparse
import sys

from peche.spatial.reg_link import build_matches


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Outils spatiaux peche-agent.")
    sub = parser.add_subparsers(dest="command")
    link = sub.add_parser("link", help="Associe plans RegPec aux entités LCE.")
    link.set_defaults(func=lambda _a: _cmd_link())
    zp = sub.add_parser(
        "zones-peche",
        help="Sync polygones zones de pêche (SmartFaune → GeoJSON).",
    )
    zp.add_argument(
        "--use-cache",
        action="store_true",
        help="Réutiliser data/cache/zones_chasse_raw.geojson",
    )
    zp.set_defaults(func=_cmd_zones_peche)
    pl = sub.add_parser(
        "plans-regpec",
        help="Harvest polygones plans RegPec → GeoJSON offline.",
    )
    pl.set_defaults(func=_cmd_plans_regpec)
    argv = list(argv if argv is not None else sys.argv[1:])
    if not argv:
        argv = ["link"]
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1
    return args.func(args)


def _cmd_link() -> int:
    result = build_matches()
    print(
        f"Liens RegPec↔LCE : {result['nb_matches']} plans, "
        f"{result['nb_with_lce']} avec match LCE"
    )
    return 0


def _cmd_zones_peche(args: argparse.Namespace) -> int:
    from peche.spatial.zones_peche import sync

    sync(use_cache=bool(args.use_cache))
    return 0


def _cmd_plans_regpec(_args: argparse.Namespace) -> int:
    from peche.spatial.plan_geom import sync_offline_plans

    sync_offline_plans()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
