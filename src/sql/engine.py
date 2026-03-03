from __future__ import annotations

import asyncpg

from src.parser.intents import Intent, IntentType
from src.sql.queries import build_query


async def execute_intent(
    pool: asyncpg.Pool,
    intent: Intent,
    sql_timeout_seconds: float,
) -> int | float | str | dict | list:
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

        if intent.intent_type == IntentType.VIDEO_DETAIL:
            row = await connection.fetchrow(query, *params, timeout=sql_timeout_seconds)
            if row is None:
                return "Видео не найдено"
            result = dict(row)
            result["_result_type"] = "video_detail"
            return result

        if intent.intent_type == IntentType.TOP_CREATORS:
            rows = await connection.fetch(query, *params, timeout=sql_timeout_seconds)
            if not rows:
                return "Нет данных"
            metric = intent.params.get("metric", "count")
            return [
                {"creator_id": str(r["creator_id"]), "value": int(r["value"]), "_result_type": "top_creators", "_metric": metric}
                for r in rows
            ]

        if intent.intent_type == IntentType.TIME_SERIES:
            rows = await connection.fetch(query, *params, timeout=sql_timeout_seconds)
            if not rows:
                return "Нет данных"
            metric = intent.params.get("metric", "")
            return [
                {"day": str(r["day"]), "value": int(r["value"]), "_result_type": "time_series", "_metric": metric}
                for r in rows
            ]

        # AGGREGATE → одно число (или дата-строка для video_created_at)
        value = await connection.fetchval(query, *params, timeout=sql_timeout_seconds)
        metric = intent.params.get("metric", "")
        if metric == "video_created_at":
            if value is None:
                return "Нет данных"
            return str(value)
        if value is None:
            # SUM/AVG возвращают NULL при отсутствии строк; COUNT всегда возвращает число
            return 0  # COUNT(*) = 0 при пустом наборе; SUM/AVG без строк тоже даём 0
        operation = intent.params.get("operation", "")
        if operation == "AVG":
            return round(float(value), 2)
        return int(value)
