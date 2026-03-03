from __future__ import annotations

import asyncpg

from src.parser.intents import Intent, IntentType
from src.sql.queries import build_query


async def execute_intent(
    pool: asyncpg.Pool,
    intent: Intent,
    sql_timeout_seconds: float,
) -> int | float | str | list | dict:
    if intent.intent_type == IntentType.UNKNOWN:
        return 0

    query, params = build_query(intent)

    async with pool.acquire() as connection:

        if intent.intent_type == IntentType.VIDEO_DATE_RANGE:
            row = await connection.fetchrow(query, *params, timeout=sql_timeout_seconds)
            if not row or not row["min_date"] or not row["max_date"]:
                return "Нет данных"
            return f"{row['min_date']} — {row['max_date']}"

        if intent.intent_type == IntentType.VIDEO_DETAIL:
            row = await connection.fetchrow(query, *params, timeout=sql_timeout_seconds)
            if not row:
                return "Видео не найдено"
            return dict(row)

        if intent.intent_type == IntentType.TOP_N:
            rows = await connection.fetch(query, *params, timeout=sql_timeout_seconds)
            metric = intent.params["metric"]
            return [
                {"_type": "top_n", "video_id": r["video_id"], "metric": metric, "value": int(r[metric])}
                for r in rows
            ]

        if intent.intent_type == IntentType.TOP_CREATORS:
            rows = await connection.fetch(query, *params, timeout=sql_timeout_seconds)
            metric = intent.params["metric"]
            return [
                {"_type": "top_creators", "creator_id": r["creator_id"], "metric": metric, "value": int(r["value"])}
                for r in rows
            ]

        if intent.intent_type == IntentType.TIME_SERIES:
            rows = await connection.fetch(query, *params, timeout=sql_timeout_seconds)
            metric = intent.params["metric"]
            return [
                {"_type": "time_series", "day": str(r["day"]), "metric": metric, "value": int(r["value"])}
                for r in rows
            ]

        # AGGREGATE → одно число
        value = await connection.fetchval(query, *params, timeout=sql_timeout_seconds)
        if value is None:
            return 0
        operation = intent.params.get("operation", "")
        if operation == "AVG":
            return round(float(value), 2)
        return int(value)
