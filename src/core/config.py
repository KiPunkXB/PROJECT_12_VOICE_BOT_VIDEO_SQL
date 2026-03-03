from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    database_url: str
    sql_timeout_seconds: float = 2.0


def get_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:5432/video_analytics",
    )
    timeout_raw = os.getenv("SQL_TIMEOUT_SECONDS", "2")
    timeout = float(timeout_raw)
    return Settings(
        telegram_bot_token=token,
        database_url=database_url,
        sql_timeout_seconds=timeout,
    )

