"""Day-by-day Telegram -> Immich sync.

For every chat and every day in the range:

    MEDIA_PATH/<chat>/<YYYY-MM-DD>/export.json     tdl chat export (that day only)
    MEDIA_PATH/<chat>/<YYYY-MM-DD>/<album>/TG_...  tdl dl, one folder per config album accepting the day

then one `immich-go upload from-folder --into-album=<album>` per chat and album over that album's
day folders that received media. One run per album (not one per chat) because immich-go drops the
album of a file it has already seen in the same run, so a day shared by two albums would end up in
only one of them; across runs it adds the existing server asset to the album.
"""

from __future__ import annotations

import json
import logging
import subprocess
from collections import defaultdict
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Self

from pydantic import BaseModel, Field, model_validator

from config import Config
from settings import Settings

log = logging.getLogger(__name__)

TDL_TEMPLATE = 'TG_{{ formatDate .MessageDate "20060102_150405" }}_{{ .MessageID }}_{{ filenamify .FileName }}'
EXPORT_NAME = "export.json"


class SyncRequest(BaseModel):
    """What to sync. Plain data, so a cron job / queue / HTTP handler can build it later.

    Either an explicit `date_from`..`date_to` range, or `catch_up`: per chat, from the last synced day
    (newest YYYY-MM-DD folder) minus `catch_up_days` through today; with no folders yet, from the earliest
    config `filters.from` (or the last `catch_up_days` days when the chat has no date-filtered albums).
    """

    date_from: date | None = None
    date_to: date | None = None
    catch_up: bool = False
    catch_up_days: int = Field(default=2, ge=0, description="Days to re-sync before the last synced one")
    chats: list[int] = Field(default_factory=list, description="Empty = every chat in the config")
    dry_run: bool = False

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.catch_up:
            if self.date_from or self.date_to:
                raise ValueError("catch_up and date_from/date_to are mutually exclusive")
        elif self.date_from is None or self.date_to is None:
            raise ValueError("either catch_up or both date_from and date_to are required")
        elif self.date_to < self.date_from:
            raise ValueError(f"date_to ({self.date_to}) is before date_from ({self.date_from})")
        return self

    @classmethod
    def last_days(cls, n: int, **kwargs: object) -> Self:
        """The last `n` days ending today (n=2 -> yesterday and today)."""
        today = date.today()
        return cls(date_from=today - timedelta(days=n - 1), date_to=today, **kwargs)


def run_sync(req: SyncRequest, settings: Settings, cfg: Config) -> None:
    chats = req.chats or cfg.chats()
    unknown = [c for c in chats if c not in cfg.chats()]
    if unknown:
        raise ValueError(f"chat id(s) {unknown} not found in config; known: {cfg.chats()}")

    for chat in chats:
        if req.catch_up:
            start, end = _catch_up_range(chat, req.catch_up_days, settings, cfg)
        else:
            assert req.date_from and req.date_to  # validated
            start, end = req.date_from, req.date_to
        log.info("chat %s: syncing %s .. %s", chat, start, end)
        by_album: dict[str, list[Path]] = defaultdict(list)
        for day in _days(start, end):
            for album_dir in _sync_day(chat, day, req, settings, cfg):
                by_album[album_dir.name].append(album_dir)
        if not by_album:
            log.info("chat %s: nothing to upload", chat)
            continue
        for i, (album, dirs) in enumerate(by_album.items(), start=1):
            log_file = settings.log_path / f"immich-go-{chat}-{datetime.now():%Y%m%d-%H%M%S}-{i}.log"
            _run(
                [
                    settings.immich_go_path,
                    "upload",
                    "from-folder",
                    f"--server={settings.immich_api_url}",
                    f"--api-key={settings.immich_api_key}",
                    f"--into-album={album}",
                    "--pause-immich-jobs=false",
                    "--concurrent-tasks=2",
                    "--no-ui",
                    "--on-errors=continue",
                    f"--log-file={log_file}",
                    *(["--dry-run"] if req.dry_run else []),
                    *map(str, dirs),
                ],
                dry_run=req.dry_run,
                secret=settings.immich_api_key,
            )


def _catch_up_range(chat: int, overlap: int, settings: Settings, cfg: Config) -> tuple[date, date]:
    today = date.today()
    chat_dir = settings.media_path / str(chat)
    synced = [d for p in chat_dir.iterdir() if (d := _parse_day(p.name))] if chat_dir.is_dir() else []
    if synced:
        return max(synced) - timedelta(days=overlap), today
    ranged = cfg.ranged_entries_for(chat)
    if ranged:
        start = min(e.filters.from_ for e in ranged if e.filters)
        log.info("chat %s: nothing synced yet, backfilling from the earliest config date %s", chat, start)
        return start, today
    log.info("chat %s: nothing synced yet and no date-filtered albums; run with --from once for history", chat)
    return today - timedelta(days=overlap), today


def _parse_day(name: str) -> date | None:
    try:
        return date.fromisoformat(name)
    except ValueError:
        return None


def _days(start: date, end: date) -> Iterator[date]:
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


def _sync_day(chat: int, day: date, req: SyncRequest, settings: Settings, cfg: Config) -> list[Path]:
    """Export + download one chat/day. Returns the album folders that have media to upload."""
    entries = [e for e in cfg.entries_for(chat) if e.accepts(day)]
    if not entries:
        log.info("chat %s %s: no album covers this day, skipping", chat, day)
        return []

    day_dir = settings.media_path / str(chat) / day.isoformat()
    export = day_dir / EXPORT_NAME
    if not req.dry_run:
        day_dir.mkdir(parents=True, exist_ok=True)

    start = datetime.combine(day, time.min).astimezone()
    end = start + timedelta(days=1, seconds=-1)
    _run(
        [settings.tdl_path, "chat", "export", "-c", str(chat), "-T", "time",
         "-i", f"{int(start.timestamp())},{int(end.timestamp())}", "-o", str(export)],
        dry_run=req.dry_run,
    )  # fmt: skip

    if not req.dry_run:
        with open(export, encoding="utf-8") as f:
            messages = len(json.load(f)["messages"])
        if not messages:
            log.info("chat %s %s: no media messages, skipping", chat, day)
            return []
        log.info("chat %s %s: %d media message(s) -> %s", chat, day, messages, [e.album for e in entries])

    for e in entries:
        _run(
            [settings.tdl_path, "dl", "-f", str(export), "-d", str(day_dir / e.album),
             "--skip-same", "--continue", "--template", TDL_TEMPLATE],
            dry_run=req.dry_run,
        )  # fmt: skip

    album_dirs = [day_dir / e.album for e in entries]
    if req.dry_run:
        return album_dirs
    return [d for d in album_dirs if any(p.is_file() for p in d.glob("*"))]


def _run(argv: list[str], *, dry_run: bool, secret: str | None = None) -> None:
    shown = " ".join(a.replace(secret, "***") if secret else a for a in argv)
    if dry_run:
        log.info("[dry-run] %s", shown)
        return
    log.debug("$ %s", shown)
    subprocess.run(argv, check=True)
