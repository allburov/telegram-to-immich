#!/bin/sh
# Background job: sync the last SYNC_DAYS days (default 2 = yesterday + today) into Immich
# every SYNC_INTERVAL (default 6h, any `sleep` duration: 30m, 6h, 1d).
# Exits on the first failed sync, so the container stops (or restarts, with a restart policy).
# Used as the Docker CMD.
set -eu
DAYS="${SYNC_DAYS:-2}"
INTERVAL="${SYNC_INTERVAL:-6h}"
while true; do
  echo "[$(date -Is)] sync last $DAYS day(s)"
  python src/main.py --last-days "$DAYS"
  echo "[$(date -Is)] next run in $INTERVAL"
  sleep "$INTERVAL"
done
