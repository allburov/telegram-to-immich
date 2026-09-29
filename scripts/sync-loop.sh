#!/bin/sh
# Background job: catch-up sync (last synced day - 2 .. today, first run backfills history)
# every SYNC_INTERVAL (default 6h, any `sleep` duration: 30m, 6h, 1d).
# Exits on the first failed sync, so the container stops (or restarts, with a restart policy).
# Used as the Docker CMD.
set -eu
INTERVAL="${SYNC_INTERVAL:-6h}"
while true; do
  echo "[$(date -Is)] sync start"
  python src/main.py --catch-up
  echo "[$(date -Is)] next run in $INTERVAL"
  sleep "$INTERVAL"
done
