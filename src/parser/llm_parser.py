from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from openai import AsyncOpenAI

from src.core.config import Settings
from src.parser.intents import Intent, IntentType


SYSTEM_PROMPT = """Ты NLU-парсер запросов к аналитике видео.
Твоя задача: преобразовать русский запрос пользователя в JSON интента.

Разрешенные intent_type:
- COUNT_VIDEOS_ALL
- COUNT_VIDEOS_CREATOR_DATE_RANGE
- COUNT_VIDEOS_VIEWS_GT
- SUM_DELTA_VIEWS_DAY
- COUNT_DISTINCT_VIDEOS_WITH_NEW_VIEWS_DAY
- VIDEO_DATE_RANGE
- UNKNOWN

Правила:
1) Возвращай ТОЛЬКО JSON.
2) Никакого SQL.
3) Если не уверен — UNKNOWN.
4) Для дат используй формат YYYY-MM-DD.
5) end_date для диапазона указывай как последний день диапазона включительно.
6) creator_id возвращай строкой.
7) threshold возвращай числом.
"""


def _parse_date(date_value: str) -> datetime:
    return datetime.strptime(date_value, "%Y-%m-%d")


def _payload_to_intent(payload: dict[str, Any]) -> Intent:
    raw_type = str(payload.get("intent_type", "UNKNOWN")).strip()
    try:
        intent_type = IntentType(raw_type)
    except ValueError:
        return Intent(IntentType.UNKNOWN, {})

    if intent_type == IntentType.COUNT_VIDEOS_ALL:
        return Intent(intent_type, {})

    if intent_type == IntentType.COUNT_VIDEOS_VIEWS_GT:
        threshold = payload.get("threshold")
        if threshold is None:
            return Intent(IntentType.UNKNOWN, {})
        try:
            return Intent(intent_type, {"threshold": int(threshold)})
        except (TypeError, ValueError):
            return Intent(IntentType.UNKNOWN, {})

    if intent_type in {
        IntentType.SUM_DELTA_VIEWS_DAY,
        IntentType.COUNT_DISTINCT_VIDEOS_WITH_NEW_VIEWS_DAY,
    }:
        start_date = payload.get("start_date")
        if not start_date:
            return Intent(IntentType.UNKNOWN, {})
        try:
            start = _parse_date(str(start_date))
        except ValueError:
            return Intent(IntentType.UNKNOWN, {})
        return Intent(intent_type, {"start": start, "end": start + timedelta(days=1)})

    if intent_type == IntentType.COUNT_VIDEOS_CREATOR_DATE_RANGE:
        creator_id = payload.get("creator_id")
        start_date = payload.get("start_date")
        end_date = payload.get("end_date")
        if not creator_id or not start_date or not end_date:
            return Intent(IntentType.UNKNOWN, {})
        try:
            start = _parse_date(str(start_date))
            end = _parse_date(str(end_date)) + timedelta(days=1)
        except ValueError:
            return Intent(IntentType.UNKNOWN, {})
        return Intent(intent_type, {"creator_id": str(creator_id), "start": start, "end": end})

    if intent_type == IntentType.VIDEO_DATE_RANGE:
        return Intent(intent_type, {})

    return Intent(IntentType.UNKNOWN, {})


async def parse_intent_with_llm(text: str, settings: Settings) -> Intent:
    if not settings.llm_parser_enabled or not settings.openai_api_key:
        return Intent(IntentType.UNKNOWN, {})

    client = AsyncOpenAI(api_key=settings.openai_api_key)
    try:
        response = await client.chat.completions.create(
            model=settings.openai_model,
            temperature=0,
            response_format={"type": "json_object"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": text},
            ],
        )
    except Exception:
        return Intent(IntentType.UNKNOWN, {})

    content = response.choices[0].message.content or "{}"
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return Intent(IntentType.UNKNOWN, {})
    if not isinstance(payload, dict):
        return Intent(IntentType.UNKNOWN, {})
    return _payload_to_intent(payload)

