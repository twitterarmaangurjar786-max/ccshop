"""Application configuration loaded from environment variables."""
from __future__ import annotations

from functools import lru_cache
from typing import List
from urllib.parse import quote

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict



class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Telegram ---
    bot_token: str
    owner_ids: List[int] = []

    # --- Database ---
    postgres_user: str = "marketplace"
    postgres_password: str = "marketplace"
    postgres_db: str = "marketplace"
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    # --- Redis ---
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    # --- Commission ---
    default_seller_percent: int = 90
    default_owner_percent: int = 10

    # --- Reservation ---
    reservation_minutes: int = 5

    # --- Crypto ---
    tron_api_key: str = ""
    tron_network: str = "mainnet"
    usdt_trc20_contract: str = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    deposit_master_wallet: str = ""

    # --- xRocket Pay (Telegram crypto payments) ---
    xrocket_api_key: str = ""
    xrocket_base_url: str = "https://pay.xrocket.tg"
    xrocket_currency: str = "USDT"

    # --- Manual payment (owner-approved) ---
    manual_bep20_address: str = ""
    manual_payment_label: str = "USDT (BEP20 / BSC)"


    # --- Misc ---
    rate_limit_per_second: int = 3
    log_level: str = "INFO"
    timezone: str = "UTC"
    currency_symbol: str = "$"

    @field_validator("owner_ids", mode="before")
    @classmethod
    def _parse_owner_ids(cls, value):
        if isinstance(value, str):
            return [int(x.strip()) for x in value.split(",") if x.strip()]
        if isinstance(value, int):
            return [value]
        return value or []

    @property
    def database_url(self) -> str:
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        return (
            f"postgresql+asyncpg://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        user = quote(self.postgres_user, safe="")
        password = quote(self.postgres_password, safe="")
        return (
            f"postgresql+psycopg2://{user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def redis_url(self) -> str:
        auth = f":{quote(self.redis_password, safe='')}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"


    def is_owner(self, telegram_id: int) -> bool:
        return telegram_id in self.owner_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
