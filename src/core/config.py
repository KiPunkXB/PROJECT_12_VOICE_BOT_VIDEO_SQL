from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    telegram_bot_token: str
    database_url: str
    sql_timeout_seconds: float = 2.0
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    llm_parser_enabled: bool = True


def get_settings() -> Settings:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:15432/video_analytics",
    )
    timeout_raw = os.getenv("SQL_TIMEOUT_SECONDS", "2")
    timeout = float(timeout_raw)
    llm_enabled_raw = os.getenv("LLM_PARSER_ENABLED", "1").strip().lower()
    llm_enabled = llm_enabled_raw not in {"0", "false", "no", "off"}
    return Settings(
        telegram_bot_token=token,
        database_url=database_url,
        sql_timeout_seconds=timeout,
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        llm_parser_enabled=llm_enabled,
    )
