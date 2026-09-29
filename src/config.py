"""Schema and loader for the tg-to-immich sync config (.data/config/tg-to-immich.yaml)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DateFilter(StrictModel):
    """Only media posted within [from, to] (inclusive) is taken."""

    from_: date = Field(alias="from", description="First day of the range")
    to: date = Field(description="Last day of the range")

    @model_validator(mode="after")
    def _check_range(self) -> Self:
        if self.to < self.from_:
            raise ValueError(f"'to' ({self.to}) is before 'from' ({self.from_})")
        return self

    def contains(self, day: date) -> bool:
        return self.from_ <= day <= self.to


class TelegramSource(StrictModel):
    """Telegram chat to pull media from, optionally narrowed by filters."""

    chat: int = Field(description="Telegram chat id")
    filters: DateFilter | None = Field(default=None, description="Optional date range filter")


class SyncEntry(StrictModel):
    """One Immich album fed from one Telegram chat (optionally a date range of it)."""

    album: str = Field(description="Immich album name")
    telegram: TelegramSource

    @property
    def chat(self) -> int:
        return self.telegram.chat

    @property
    def filters(self) -> DateFilter | None:
        return self.telegram.filters

    def accepts(self, day: date) -> bool:
        return self.filters is None or self.filters.contains(day)


class Config(StrictModel):
    sync: list[SyncEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_entries(self) -> Self:
        by_chat: dict[int, list[SyncEntry]] = defaultdict(list)
        for e in self.sync:
            by_chat[e.chat].append(e)
        for chat, entries in by_chat.items():
            names = [e.album for e in entries]
            dupes = sorted({n for n in names if names.count(n) > 1})
            if dupes:
                raise ValueError(f"chat {chat}: duplicate album names {dupes}")
            ranged = sorted(((e.filters, e.album) for e in entries if e.filters is not None), key=lambda x: x[0].from_)
            for (prev, prev_album), (cur, cur_album) in zip(ranged, ranged[1:], strict=False):
                if cur.from_ <= prev.to:
                    raise ValueError(f"chat {chat}: filters of albums {prev_album!r} and {cur_album!r} overlap")
        return self

    def chats(self) -> list[int]:
        seen: dict[int, None] = {}
        for e in self.sync:
            seen.setdefault(e.chat, None)
        return list(seen)

    def entries_for(self, chat: int) -> list[SyncEntry]:
        return [e for e in self.sync if e.chat == chat]

    def ranged_entries_for(self, chat: int) -> list[SyncEntry]:
        return [e for e in self.sync if e.chat == chat and e.filters is not None]

    def ranged_album_for(self, chat: int, day: date) -> SyncEntry | None:
        """Date-filtered album of `chat` whose range contains `day`, if any."""
        return next((e for e in self.ranged_entries_for(chat) if e.accepts(day)), None)

    @classmethod
    def load(cls, path: str | Path) -> Self:
        with open(path, encoding="utf-8") as f:
            return cls.model_validate(yaml.safe_load(f))
