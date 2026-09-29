# Run from the repo root: Settings reads ./.env, config is ./.data/config/tg-to-immich.yaml
# Cron example (every 6h):  0 */6 * * * cd /path/to/telegram-to-immich && make sync >> .data/logs/cron.log 2>&1

.PHONY: install lint fmt sync build

install:
	uv sync

lint:
	uv run ruff check src scripts
	uv run ruff format --check src scripts
	uv run mypy

fmt:
	uv run ruff format src scripts
	uv run ruff check --fix src scripts

# yesterday + today -> Immich
sync:
	uv run python src/main.py --last-days 2

build:
	docker build -t allburov/telegram-to-immich .
