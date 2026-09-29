#!/usr/bin/env python3
"""Sync a date range of Telegram chats into Immich, one folder per chat and day.

Usage (from the repo root, reads ./.env and .data/config/tg-to-immich.yaml):
    uv run python src/main.py --from 2025-09-01 --to 2025-09-07
    uv run python src/main.py --from 2025-09-01 --chat 1000000002 --dry-run
    uv run python src/main.py --last-days 2            # yesterday + today (what `make sync` runs)
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import date

from config import Config
from settings import Settings
from sync import SyncRequest, run_sync


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--from", dest="date_from", type=date.fromisoformat, help="First day (YYYY-MM-DD)")
    ap.add_argument("--to", dest="date_to", type=date.fromisoformat, help="Last day, defaults to --from")
    ap.add_argument("--last-days", type=int, help="Sync the last N days ending today (instead of --from/--to)")
    ap.add_argument("--chat", action="append", type=int, default=[], help="Only this chat id. Repeatable.")
    ap.add_argument("-n", "--dry-run", action="store_true", help="Print the tdl/immich-go commands, run nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    if args.last_days:
        req = SyncRequest.last_days(args.last_days, chats=args.chat, dry_run=args.dry_run)
    elif args.date_from:
        req = SyncRequest(
            date_from=args.date_from, date_to=args.date_to or args.date_from, chats=args.chat, dry_run=args.dry_run
        )
    else:
        ap.error("give --from [--to] or --last-days")

    settings = Settings()  # required fields come from .env
    cfg = Config.load(settings.config_path)
    try:
        run_sync(req, settings, cfg)
    except ValueError as e:
        print(e, file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
