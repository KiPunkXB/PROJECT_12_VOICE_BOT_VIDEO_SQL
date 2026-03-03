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
    log_level: str = "INFO"
    llm_debug_logging: bool = False
    hybrid_intent_cache_size: int = 500
    llm_compact_prompt_enabled: bool = True
    llm_compact_retry_full: bool = True


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
    llm_debug_raw = os.getenv("LLM_DEBUG_LOGGING", "0").strip().lower()
    llm_debug_logging = llm_debug_raw in {"1", "true", "yes", "on"}
    log_level = (os.getenv("LOG_LEVEL", "INFO").strip() or "INFO").upper()
    cache_size_raw = os.getenv("HYBRID_INTENT_CACHE_SIZE", "500").strip()
    try:
        hybrid_intent_cache_size = max(0, int(cache_size_raw))
    except ValueError:
        hybrid_intent_cache_size = 500
    compact_prompt_raw = os.getenv("LLM_COMPACT_PROMPT_ENABLED", "1").strip().lower()
    llm_compact_prompt_enabled = compact_prompt_raw not in {"0", "false", "no", "off"}
    compact_retry_raw = os.getenv("LLM_COMPACT_RETRY_FULL", "0").strip().lower()
    llm_compact_retry_full = compact_retry_raw not in {"0", "false", "no", "off"}
    return Settings(
        telegram_bot_token=token,
        database_url=database_url,
        sql_timeout_seconds=timeout,
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
        llm_parser_enabled=llm_enabled,
        log_level=log_level,
        llm_debug_logging=llm_debug_logging,
        hybrid_intent_cache_size=hybrid_intent_cache_size,
        llm_compact_prompt_enabled=llm_compact_prompt_enabled,
        llm_compact_retry_full=llm_compact_retry_full,
    )
