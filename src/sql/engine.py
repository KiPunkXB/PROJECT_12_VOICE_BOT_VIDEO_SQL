from __future__ import annotations

import asyncpg

from src.parser.intents import Intent, IntentType
from src.sql.queries import build_query


async def execute_intent(
    pool: asyncpg.Pool,
    intent: Intent,
    sql_timeout_seconds: float,
) -> int | float | str:
    if intent.intent_type == IntentType.UNKNOWN:
        return 0

    query, params = build_query(intent)

    async with pool.acquire() as connection:

        if intent.intent_type == IntentType.VIDEO_DATE_RANGE:
            row = await connection.fetchrow(query, *params, timeout=sql_timeout_seconds)
            if not row or not row["min_date"] or not row["max_date"]:
                return "Нет данных"
            return f"{row['min_date']} — {row['max_date']}"

        if intent.intent_type == IntentType.LOOKUP_ID:
            value = await connection.fetchval(query, *params, timeout=sql_timeout_seconds)
            if value is None:
                return "Нет данных"
            return str(value)

        # AGGREGATE → одно число
        value = await connection.fetchval(query, *params, timeout=sql_timeout_seconds)
        if value is None:
            return 0
        operation = intent.params.get("operation", "")
        if operation == "AVG":
            return round(float(value), 2)
        return int(value)
