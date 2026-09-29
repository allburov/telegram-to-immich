# telegram-to-immich

Sync photos and videos from Telegram chats into [Immich](https://immich.app) albums.

Built on [tdl](https://github.com/iyear/tdl) (Telegram export and download) and
[immich-go](https://github.com/simulot/immich-go) (Immich upload). Point it at a chat, say which
date ranges go into which albums, and run it on a schedule. Re-running the same days is safe: media
already downloaded or already in Immich is skipped.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/) (or Docker, see below)
- `tdl` and `immich-go` installed, and `tdl login` done
- An Immich API key

## Configuration

**Albums** live in `.data/config/tg-to-immich.yaml`. Each entry maps one Telegram chat, optionally narrowed
to a date range, to one Immich album. Ranges of the same chat must not overlap; an entry without
`filters` takes every day.

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

**Connection and paths** come from environment variables or `./.env` (copy `.env.example`):

| Variable         | Default                          | Meaning                                                                |
|------------------|----------------------------------|------------------------------------------------------------------------|
| `IMMICH_API_URL` | required                         | Immich server, e.g. `http://immich.local:2283`                         |
| `IMMICH_API_KEY` | required                         | Immich API key                                                         |
| `IMMICH_GO_PATH` | `immich-go`                      | immich-go binary                                                       |
| `TDL_PATH`       | `tdl`                            | tdl binary                                                             |
| `MEDIA_PATH`     | `.data/media`                    | where downloaded media is kept                                         |
| `LOG_PATH`       | `.data/logs`                     | immich-go log files                                                    |
| `CONFIG_PATH`    | `.data/config/tg-to-immich.yaml` | album config                                                           |
| `SYNC_INTERVAL`  | `6h`                             | Docker only: how often the catch-up sync runs (`30m`, `6h`, `1d`)      |
| `TZ`             | system                           | timezone used for day boundaries                                       |

Everything the tool writes or reads lives under `.data/`: `config/`, `media/`, `logs/` and, with Docker, `tdl/`.

## Usage

```sh
make install

uv run python src/main.py --from 2025-09-01 --to 2025-09-07     # a date range, all chats
uv run python src/main.py --from 2025-09-01 --chat 1000000002   # one day, one chat
uv run python src/main.py --last-days 2 --dry-run               # show what would run

make sync                                                      # catch up: see below
make sync-last-2-days                                          # yesterday + today
```

`make sync` (and the Docker loop) continues from where it left off: for each chat it takes the newest
synced day, goes back 2 days (`--catch-up-days`) to pick up late additions, and syncs through today. On the first run it
backfills from the earliest date in the album config, or just the last 2 days for chats without date
ranges (use `--from` once for their history).

```sh
```

To run it on a schedule without Docker, use cron:

```
0 */6 * * * cd /path/to/telegram-to-immich && make sync >> .data/logs/cron.log 2>&1
```

## Docker

The image bundles tdl, immich-go and a loop that runs the catch-up sync every `SYNC_INTERVAL`.
`docker-compose.yaml` keeps everything, including the Telegram session, under `./.data`.

```sh
cp .env.example .env                           # fill in IMMICH_API_URL / IMMICH_API_KEY
docker compose build                           # or `docker compose pull`

docker compose run --rm sync tdl login -T qr   # scan the QR code with the Telegram app
docker compose run --rm sync tdl chat ls       # chat ids for .data/config/tg-to-immich.yaml

docker compose up -d
docker compose logs -f
```

`tdl login` also accepts `-T code` (phone number + SMS code). The session is stored in `/data/tdl`, i.e. `.data/tdl` on the host,
so don't run a host `tdl` against it while the container is up. Any other tdl or sync command can be
run the same way, e.g. `docker compose run --rm sync python src/main.py --catch-up --dry-run`.

The container exits on a failed sync (a missing login included) and Docker restarts it; see
`docker compose logs` for the error.

## License

[MIT](LICENSE)
