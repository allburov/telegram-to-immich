# telegram-to-immich

Sync photos and videos from Telegram chats into [Immich](https://immich.app) albums.

Point it at a chat (a class group, a family chat, a channel), say which date ranges go into which
albums, and it keeps Immich up to date: every few hours it picks up the new days, downloads their media
and uploads it into the right album. Re-running the same days is safe, media that is already
downloaded or already in Immich is skipped.

Built on [tdl](https://github.com/iyear/tdl) (Telegram export and download) and
[immich-go](https://github.com/simulot/immich-go) (Immich upload).

## Install (Docker Compose)

```sh
mkdir telegram-to-immich && cd telegram-to-immich
wget https://raw.githubusercontent.com/allburov/telegram-to-immich/main/docker-compose.yaml
wget https://raw.githubusercontent.com/allburov/telegram-to-immich/main/.env.example -O .env
```

1. Edit `.env`: set `IMMICH_API_URL` and `IMMICH_API_KEY` (Immich → Account settings → API keys).
2. Log in to Telegram once. The session is kept in `.data/tdl`:

   ```sh
   docker compose run --rm sync tdl login -T qr   # scan the QR code with the Telegram app
   ```

   `-T code` logs in with a phone number and SMS code instead.
3. Find the chat ids and write the album config:

   ```sh
   docker compose run --rm sync tdl chat ls
   mkdir -p .data/config && nano .data/config/tg-to-immich.yaml   # see Configuration below
   ```
4. Start it:

   ```sh
   docker compose up -d
   docker compose logs -f
   ```

The container syncs on start and then every `SYNC_INTERVAL` (default 6h). It exits on a failed sync
(a missing login included) and Docker restarts it; `docker compose logs` shows the error. Don't run a
host `tdl` against `.data/tdl` while the container is up.

Any other command can be run through the same image, for example
`docker compose run --rm sync python src/main.py --catch-up --dry-run`.

## Configuration

**Albums** live in `.data/config/tg-to-immich.yaml`. Each entry maps one Telegram chat, optionally
narrowed to a date range, to one Immich album. Ranges of the same chat must not overlap; an entry
without `filters` takes every day.

```yaml
sync:
  - album: 'Family trips'
    telegram:
      chat: 1000000001              # tdl chat ls

  - album: '1st grade'
    telegram:
      chat: 1000000002
      filters: { from: 2024-08-01, to: 2025-07-31 }

  - album: '2nd grade'
    telegram:
      chat: 1000000002
      filters: { from: 2025-08-01, to: 2026-07-31 }
```

**Connection and paths** come from environment variables or `./.env`:

| Variable         | Default                          | Meaning                                                           |
|------------------|----------------------------------|-------------------------------------------------------------------|
| `IMMICH_API_URL` | required                         | Immich server, e.g. `http://immich.local:2283`                    |
| `IMMICH_API_KEY` | required                         | Immich API key                                                    |
| `SYNC_INTERVAL`  | `6h`                             | Docker only: how often the sync runs (`30m`, `6h`, `1d`)          |
| `TZ`             | system                           | timezone used for day boundaries                                  |
| `CONFIG_PATH`    | `.data/config/tg-to-immich.yaml` | album config                                                      |
| `MEDIA_PATH`     | `.data/media`                    | where downloaded media is kept                                    |
| `LOG_PATH`       | `.data/logs`                     | immich-go log files                                               |
| `TDL_PATH`       | `tdl`                            | tdl binary                                                        |
| `IMMICH_GO_PATH` | `immich-go`                      | immich-go binary                                                  |

Everything the tool writes or reads lives under `.data/`: `config/`, `media/`, `logs/` and `tdl/`.

## How it works

Media is synced one day at a time. For each chat and day, that day's messages are exported from
Telegram and their media downloaded into a folder per album:

```
.data/media/<chat id>/<YYYY-MM-DD>/export.json
.data/media/<chat id>/<YYYY-MM-DD>/<album>/TG_<date>_<time>_<message id>_<file name>
```

Then immich-go uploads the new day folders, using the album folder name as the Immich album.

A scheduled run (`--catch-up`) continues from where it left off: for each chat it takes the newest
synced day folder, goes back 2 days (`--catch-up-days`) to pick up late additions, and syncs through
today. On the first run it backfills from the earliest date in the album config, or just the last
2 days for chats without date ranges (run `--from` once for their history).

## Running locally

Needs Python 3.12, [uv](https://docs.astral.sh/uv/), `tdl` (logged in) and `immich-go` on `PATH`,
plus `.env` and `.data/config/tg-to-immich.yaml` as above.

```sh
git clone https://github.com/allburov/telegram-to-immich && cd telegram-to-immich
make install

uv run python src/main.py --catch-up                             # what the container runs
uv run python src/main.py --from 2025-09-01 --to 2025-09-07      # a date range, all chats
uv run python src/main.py --from 2025-09-01 --chat 1000000002    # one day, one chat
uv run python src/main.py --last-days 2 --dry-run                # show what would run

make sync                # --catch-up
make sync-last-2-days    # yesterday + today
make lint                # ruff + mypy
make build               # docker build -t allburov/telegram-to-immich
```

## License

[MIT](LICENSE)
