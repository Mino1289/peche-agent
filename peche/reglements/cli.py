"""CLI `python3 -m peche.reglements` — wrappe `sync` et `index`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError

from peche.reglements.sync import (
    CACHE_DIR,
    build_index,
    sync_zone,
    write_index,
)
from peche.reglements.zones import ZONES, zone_by_id


def cmd_sync(args: argparse.Namespace) -> int:
    zones = ZONES
    if args.zone:
        zones = []
        for zid in args.zone:
            zone = zone_by_id(zid)
            if zone is None:
                print(f"Unknown zone id {zid}.", file=sys.stderr)
            else:
                zones.append(zone)
        if not zones:
            print("No matching zones.", file=sys.stderr)
            return 1

    failures: list[str] = []
    synced = 0
    for zone in zones:
        try:
            sync_zone(
                zone,
                args.cache_dir,
                args.timeout,
                args.delay,
                args.skip_existing,
                args.force,
            )
            synced += 1
        except (HTTPError, URLError, OSError, ValueError, json.JSONDecodeError) as exc:
            failures.append(f"{zone.text} ({zone.value}): {exc}")
            print(f"FAILED {zone.text}: {exc}", file=sys.stderr)

    index = build_index(ZONES)
    index_path = write_index(index)
    print(f"\nIndex: {index_path} ({len(index['zones'])} zones synced)")

    if failures:
        print("\nFailures:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        return 1 if synced == 0 else 0
    return 0


def cmd_index(_: argparse.Namespace) -> int:
    index = build_index(ZONES)
    path = write_index(index)
    print(f"Updated {path} ({len(index['zones'])} zones)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Sync Quebec fishing regulations into agent-ready JSON files."
    )
    sub = parser.add_subparsers(dest="command")

    sync = sub.add_parser("sync", help="Download and parse zones into data/zones/")
    sync.add_argument(
        "--zone", type=int, action="append", help="Sync only these zone IDs"
    )
    sync.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    sync.add_argument("--delay", type=float, default=0.3)
    sync.add_argument("--timeout", type=float, default=30.0)
    sync.add_argument("--skip-existing", action="store_true", help="Reuse cached HTML")
    sync.add_argument(
        "--force",
        action="store_true",
        help="Re-sync zones even if JSON already exists",
    )
    sync.set_defaults(func=cmd_sync)

    index = sub.add_parser(
        "index", help="Rebuild data/index.json from existing zone files"
    )
    index.set_defaults(func=cmd_index)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    argv = list(argv if argv is not None else sys.argv[1:])
    if argv and argv[0] not in {"sync", "index"}:
        argv = ["sync", *argv]
    elif not argv:
        argv = ["sync"]
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
