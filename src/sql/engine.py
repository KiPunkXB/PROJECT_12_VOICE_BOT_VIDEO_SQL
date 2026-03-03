from __future__ import annotations

import asyncpg

from src.parser.intents import Intent, IntentType
from src.sql.queries import build_query


async def execute_intent(
    pool: asyncpg.Pool,
    intent: Intent,
    sql_timeout_seconds: float,
) -> int:
    if intent.intent_type == IntentType.UNKNOWN:
        return 0

    query, params = build_query(intent)
    async with pool.acquire() as connection:
        value = await connection.fetchval(query, *params, timeout=sql_timeout_seconds)
    return int(value or 0)

