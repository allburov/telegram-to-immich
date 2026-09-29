"""Runtime settings, read from environment / ./.env (see .env for the keys)."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    immich_api_url: str
    immich_api_key: str
    immich_go_path: Path = Path("immich-go")
    tdl_path: str = "tdl"
    media_path: Path = Path(".data/media")
    log_path: Path = Path(".data/logs")
    config_path: Path = Path(".config/tg-to-immich.yaml")
