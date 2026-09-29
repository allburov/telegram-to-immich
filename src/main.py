#!/usr/bin/env python3
"""Sync a date range of Telegram chats into Immich, one folder per chat and day.

Usage (from the repo root, reads ./.env and .data/config/tg-to-immich.yaml):
    uv run python src/main.py --from 2025-09-01 --to 2025-09-07
    uv run python src/main.py --from 2025-09-01 --chat 1000000002 --dry-run
    uv run python src/main.py --catch-up               # last synced day - 2 .. today (`make sync`)
    uv run python src/main.py --catch-up --catch-up-days 7
    uv run python src/main.py --last-days 2            # yesterday + today (`make sync-last-2-days`)
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
    ap.add_argument(
        "--catch-up",
        action="store_true",
        help="Per chat: last synced day minus --catch-up-days through today; first run backfills from the config",
    )
    ap.add_argument("--catch-up-days", type=int, default=2, help="Overlap for --catch-up (default: 2)")
    ap.add_argument("--chat", action="append", type=int, default=[], help="Only this chat id. Repeatable.")
    ap.add_argument("-n", "--dry-run", action="store_true", help="Print the tdl/immich-go commands, run nothing")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO, format="%(message)s")

    if args.catch_up:
        if args.date_from or args.date_to or args.last_days:
            ap.error("--catch-up cannot be combined with --from/--to or --last-days")
        req = SyncRequest(catch_up=True, catch_up_days=args.catch_up_days, chats=args.chat, dry_run=args.dry_run)
    elif args.last_days:
        req = SyncRequest.last_days(args.last_days, chats=args.chat, dry_run=args.dry_run)
    elif args.date_from:
        req = SyncRequest(
            date_from=args.date_from, date_to=args.date_to or args.date_from, chats=args.chat, dry_run=args.dry_run
        )
    else:
        ap.error("give --catch-up, --last-days or --from [--to]")

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
