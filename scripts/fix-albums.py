#!/usr/bin/env python3
"""Re-shuffle downloaded media between sub-album folders after date ranges in
.data/config/tg-to-immich.yaml were changed.

Layout expected under --media-root (default .data/media):

    <chat id>/<sub-album>/TG_YYYYMMDD_HHMMSS_<msg id>_<original name>
    <chat id>/TG_...                         # media not matching any range

For every chat that has sync entries with `telegram.filters` (date ranges),
each file in the chat folder (root + one level of sub-folders) is parsed for
its date and moved into the folder named after the album whose range contains
that date. Files whose date matches no range are moved to the chat root.
Entries without filters are ignored. Nothing is ever overwritten or deleted;
conflicts are reported and the script exits non-zero.

Usage:
    uv run python scripts/fix-albums.py --dry-run
    uv run python scripts/fix-albums.py --chat 1000000002 --dry-run
    uv run python scripts/fix-albums.py --chat 1000000002
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from config import Config  # noqa: E402

FILENAME_RE = re.compile(r"^TG_(\d{4})(\d{2})(\d{2})_\d{6}_\d+_")


@dataclass
class Move:
    src: Path
    dst: Path


def parse_date(name: str) -> date | None:
    m = FILENAME_RE.match(name)
    if not m:
        return None
    try:
        return date(int(m[1]), int(m[2]), int(m[3]))
    except ValueError:
        return None


def iter_media_files(chat_dir: Path) -> Iterator[Path]:
    """Files directly in the chat dir plus files one level down (sub-albums)."""
    for p in sorted(chat_dir.iterdir()):
        if p.is_file():
            yield p
        elif p.is_dir():
            for f in sorted(p.iterdir()):
                if f.is_file():
                    yield f


def plan_chat(cfg: Config, chat: int, chat_dir: Path) -> tuple[list[Move], list[Path], list[Path]]:
    """Return (moves, unparsable, unmatched-by-range)."""
    moves: list[Move] = []
    unparsable: list[Path] = []
    unmatched: list[Path] = []

    for f in iter_media_files(chat_dir):
        day = parse_date(f.name)
        if day is None:
            unparsable.append(f)
            continue
        sub = cfg.ranged_album_for(chat, day)
        if sub is None:
            unmatched.append(f)
            target_dir = chat_dir
        else:
            target_dir = chat_dir / sub.album
        dst = target_dir / f.name
        if dst != f:
            moves.append(Move(f, dst))
    return moves, unparsable, unmatched


def rel(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=REPO_ROOT / ".data" / "config" / "tg-to-immich.yaml", type=Path)
    ap.add_argument("--media-root", default=REPO_ROOT / ".data" / "media", type=Path)
    ap.add_argument(
        "--chat",
        action="append",
        type=int,
        default=[],
        help="Only process this exact chat id (e.g. 1000000002). Repeatable. "
        "Default: all chats with date-filtered albums.",
    )
    ap.add_argument("-n", "--dry-run", action="store_true", help="Print what would be moved, change nothing")
    ap.add_argument("-v", "--verbose", action="store_true", help="List every file move, not just the summary")
    args = ap.parse_args()

    cfg = Config.load(args.config)
    media_root: Path = args.media_root.resolve()

    chats = [c for c in cfg.chats() if cfg.ranged_entries_for(c)]
    if args.chat:
        unknown = [c for c in args.chat if c not in chats]
        if unknown:
            print(
                f"Chat id(s) {unknown} not found in config among chats with date-filtered albums: {chats}",
                file=sys.stderr,
            )
            return 2
        chats = [c for c in chats if c in set(args.chat)]
    if not chats:
        print("No sync entries with date filters.", file=sys.stderr)
        return 2

    exit_code = 0
    for chat in chats:
        chat_dir = media_root / str(chat)
        albums = ", ".join(e.album for e in cfg.ranged_entries_for(chat))
        print(f"\n=== chat {chat} -> {rel(chat_dir, media_root)}/  [{albums}]")
        if not chat_dir.is_dir():
            print("  folder does not exist, skipping")
            continue

        moves, unparsable, unmatched = plan_chat(cfg, chat, chat_dir)

        # Conflicts: destination already exists (and is not the source itself).
        conflicts = [m for m in moves if m.dst.exists()]
        moves = [m for m in moves if not m.dst.exists()]

        by_route = Counter((rel(m.src.parent, chat_dir), rel(m.dst.parent, chat_dir)) for m in moves)
        if not moves:
            print("  nothing to move")
        for (src_dir, dst_dir), n in sorted(by_route.items()):
            print(f"  {n:>6}  {src_dir!s:<40} -> {dst_dir}")

        if args.verbose:
            for m in moves:
                print(f"    {rel(m.src, chat_dir)}  ->  {rel(m.dst, chat_dir)}")

        if unmatched:
            print(f"  WARNING: {len(unmatched)} file(s) match no date range, routed to chat root:")
            for p in unmatched[:10]:
                print(f"    {rel(p, chat_dir)}")
            if len(unmatched) > 10:
                print(f"    ... and {len(unmatched) - 10} more")
        if unparsable:
            print(f"  WARNING: {len(unparsable)} file(s) have no TG_YYYYMMDD_ prefix, left untouched:")
            for p in unparsable[:10]:
                print(f"    {rel(p, chat_dir)}")
            if len(unparsable) > 10:
                print(f"    ... and {len(unparsable) - 10} more")
        if conflicts:
            exit_code = 1
            print(f"  ERROR: {len(conflicts)} file(s) NOT moved, destination already exists:")
            for m in conflicts[:10]:
                print(f"    {rel(m.src, chat_dir)}  ->  {rel(m.dst, chat_dir)}")
            if len(conflicts) > 10:
                print(f"    ... and {len(conflicts) - 10} more")

        if args.dry_run:
            print(f"  [dry-run] would move {len(moves)} file(s)")
            continue

        moved = 0
        for m in moves:
            m.dst.parent.mkdir(parents=True, exist_ok=True)
            m.src.rename(m.dst)
            moved += 1
        print(f"  moved {moved} file(s)")

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
