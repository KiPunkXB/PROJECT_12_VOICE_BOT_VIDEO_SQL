from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta
from typing import Any

from openai import AsyncOpenAI

from src.core.config import Settings
from src.parser.intents import Intent, IntentType
from src.sql.queries import ALLOWED_METRICS, ALLOWED_OPERATIONS

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """Ты NLU-парсер запросов к аналитике видео на платформе.
Преобразуй русский запрос пользователя в JSON интента.

━━━━━━━━━━━━━━━━━ СХЕМА БАЗЫ ДАННЫХ ━━━━━━━━━━━━━━━━━

Таблица videos (итоговая статистика по каждому видео):
  id (= video_id)         — идентификатор видео
  creator_id              — идентификатор создателя/автора/креатора
  video_created_at        — дата и время публикации видео
  views_count             — общее число просмотров
  likes_count             — общее число лайков
  comments_count          — общее число комментариев
  reports_count           — общее число жалоб

Таблица video_snapshots (почасовые замеры):
  video_id                — ссылка на видео
  created_at              — дата и время замера (раз в час)
  views_count             — просмотры на момент замера
  likes_count             — лайки на момент замера
  comments_count          — комменты на момент замера
  reports_count           — жалобы на момент замера
  delta_views_count       — прирост просмотров с прошлого замера
  delta_likes_count       — прирост лайков с прошлого замера
  delta_comments_count    — прирост комментариев с прошлого замера
  delta_reports_count     — прирост жалоб с прошлого замера

━━━━━━━━━━━━━━━━━ ДОСТУПНЫЕ ИНТЕНТЫ ━━━━━━━━━━━━━━━━━

1. AGGREGATE — агрегация (COUNT, SUM, AVG, MAX, MIN, COUNT_DISTINCT)
2. TOP_N — топ N видео по любому полю
3. TOP_CREATORS — топ N авторов (GROUP BY creator_id)
4. TIME_SERIES — динамика по дням (GROUP BY date)
5. VIDEO_DETAIL — все поля одного конкретного видео по ID
6. VIDEO_DATE_RANGE — за какой период вообще существуют видео в базе
7. UNKNOWN — если запрос не подходит

━━━━━━━━━━━━━━━━━ ФОРМАТЫ ОТВЕТА ━━━━━━━━━━━━━━━━━━━━━

AGGREGATE:
{"intent_type":"AGGREGATE","operation":"COUNT|SUM|AVG|MAX|MIN|COUNT_DISTINCT","metric":"<поле> или *","table":"videos|video_snapshots","filters":{"creator_id":null,"video_id":null,"date_from":"YYYY-MM-DD|null","date_to":"YYYY-MM-DD|null","filter_field":null,"filter_gt":null,"filter_eq_field":null,"filter_eq_value":null}}

TOP_N:
{"intent_type":"TOP_N","metric":"<поле>","table":"videos","limit":10,"filters":{}}

TOP_CREATORS:
{"intent_type":"TOP_CREATORS","metric":"count|views_count|likes_count|comments_count|reports_count","limit":10,"filters":{"date_from":null,"date_to":null}}

TIME_SERIES:
{"intent_type":"TIME_SERIES","metric":"delta_views_count|delta_likes_count|delta_comments_count|delta_reports_count","filters":{"date_from":"YYYY-MM-DD","date_to":"YYYY-MM-DD"},"limit":0}
(limit=0 — все дни, limit=1 — только лучший/худший день)

VIDEO_DETAIL:
{"intent_type":"VIDEO_DETAIL","video_id":"<uuid>"}

━━━━━━━━━━━━━━━━━ ПРАВИЛА ━━━━━━━━━━━━━━━━━━━━━━━━━━━

1) Возвращай ТОЛЬКО JSON — без пояснений, без SQL.
2) COUNT(*) для подсчёта строк/видео.
3) SUM(поле) для суммы значений.
4) delta_* поля ТОЛЬКО в video_snapshots.
5) Прирост/рост/изменение → delta_* в video_snapshots.
6) Накопленная статистика (без "прирост"/"рост") → таблица videos.
7) date_from и date_to — ВКЛЮЧИТЕЛЬНО; код добавит +1 день для <.
8) Если год не указан → используй 2025.
9) filter_field + filter_gt для "больше N", "превысили N", "свыше N".
10) filter_eq_field + filter_eq_value для "ровно N", "без просмотров (=0)", "без лайков (=0)".
11) UNKNOWN если запрос не о видео-аналитике.
12) Не выдумывай creator_id если он явно не указан.
13) creator_id ТОЛЬКО в videos — при фильтре по creator_id всегда используй table=videos.
14) Запросы о метриках создателя → SUM/AVG из videos с фильтром creator_id.
15) "Топ авторов/создателей" → TOP_CREATORS, а не TOP_N.
16) "Динамика по дням", "в какой день больше всего" → TIME_SERIES.
17) "Покажи/расскажи про видео X" → VIDEO_DETAIL.
18) TIME_SERIES: limit=0 для всей динамики, limit=1 для лучшего дня.

━━━━━━━━━━━━━━━━━ ПРИМЕРЫ ━━━━━━━━━━━━━━━━━━━━━━━━━━━

Запрос: "сколько всего видео?"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{}}

Запрос: "скока видосов"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{}}

Запрос: "сколько видео в августе 2025"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"date_from":"2025-08-01","date_to":"2025-08-31"}}

Запрос: "скока видосов в октябре"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"}}

Запрос: "сколько видео с просмотрами больше 100000"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_field":"views_count","filter_gt":100000}}

Запрос: "сколько видео без просмотров"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"views_count","filter_eq_value":0}}

Запрос: "сколько видео без лайков"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"likes_count","filter_eq_value":0}}

Запрос: "сколько видео с жалобами"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_field":"reports_count","filter_gt":0}}

Запрос: "сколько всего креаторов"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"creator_id","table":"videos","filters":{}}

Запрос: "суммарные просмотры всех видео"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"views_count","table":"videos","filters":{}}

Запрос: "сколько лайков всего"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{}}

Запрос: "сколько жалоб за ноябрь 2025"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"reports_count","table":"videos","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Запрос: "сколько комментариев у видео ecd8a4e4-1f24"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"comments_count","table":"videos","filters":{"video_id":"ecd8a4e4-1f24"}}

Запрос: "средние просмотры на видео"
{"intent_type":"AGGREGATE","operation":"AVG","metric":"views_count","table":"videos","filters":{}}

Запрос: "максимальные лайки"
{"intent_type":"AGGREGATE","operation":"MAX","metric":"likes_count","table":"videos","filters":{}}

Запрос: "прирост просмотров 28 ноября 2025"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"delta_views_count","table":"video_snapshots","filters":{"date_from":"2025-11-28","date_to":"2025-11-28"}}

Запрос: "сколько видео получили новые просмотры 27 ноября"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"video_id","table":"video_snapshots","filters":{"date_from":"2025-11-27","date_to":"2025-11-27","filter_field":"delta_views_count","filter_gt":0}}

Запрос: "сколько видео выпустил создатель abc123"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"creator_id":"abc123"}}

Запрос: "сколько видео выпустил создатель abc123 в мае"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"creator_id":"abc123","date_from":"2025-05-01","date_to":"2025-05-31"}}

Запрос: "сколько лайков получил создатель abc123"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{"creator_id":"abc123"}}

Запрос: "сколько комментариев у автора abc за октябрь"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"comments_count","table":"videos","filters":{"creator_id":"abc","date_from":"2025-10-01","date_to":"2025-10-31"}}

Запрос: "топ 10 видео"
{"intent_type":"TOP_N","metric":"views_count","table":"videos","limit":10,"filters":{}}

Запрос: "топ 5 по лайкам"
{"intent_type":"TOP_N","metric":"likes_count","table":"videos","limit":5,"filters":{}}

Запрос: "лучшие видео по комментариям"
{"intent_type":"TOP_N","metric":"comments_count","table":"videos","limit":10,"filters":{}}

Запрос: "топ 5 видео создателя abc по просмотрам"
{"intent_type":"TOP_N","metric":"views_count","table":"videos","limit":5,"filters":{"creator_id":"abc"}}

Запрос: "у каких авторов больше всего видео"
{"intent_type":"TOP_CREATORS","metric":"count","limit":10,"filters":{}}

Запрос: "топ 3 автора по лайкам"
{"intent_type":"TOP_CREATORS","metric":"likes_count","limit":3,"filters":{}}

Запрос: "какой создатель получил больше всего жалоб"
{"intent_type":"TOP_CREATORS","metric":"reports_count","limit":1,"filters":{}}

Запрос: "топ авторов по просмотрам за ноябрь"
{"intent_type":"TOP_CREATORS","metric":"views_count","limit":10,"filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Запрос: "самый продуктивный создатель"
{"intent_type":"TOP_CREATORS","metric":"count","limit":1,"filters":{}}

Запрос: "динамика просмотров по дням за ноябрь 2025"
{"intent_type":"TIME_SERIES","metric":"delta_views_count","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"},"limit":0}

Запрос: "в какой день был максимальный прирост просмотров"
{"intent_type":"TIME_SERIES","metric":"delta_views_count","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"},"limit":1}

Запрос: "самый активный день по лайкам в ноябре"
{"intent_type":"TIME_SERIES","metric":"delta_likes_count","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"},"limit":1}

Запрос: "динамика жалоб по дням"
{"intent_type":"TIME_SERIES","metric":"delta_reports_count","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"},"limit":0}

Запрос: "покажи статистику видео ecd8a4e4-1f24-4b97-a944-35d17078ce7c"
{"intent_type":"VIDEO_DETAIL","video_id":"ecd8a4e4-1f24-4b97-a944-35d17078ce7c"}

Запрос: "что за видео ecd8a4e4-1f24?"
{"intent_type":"VIDEO_DETAIL","video_id":"ecd8a4e4-1f24"}

Запрос: "диапазон дат видео"
{"intent_type":"VIDEO_DATE_RANGE"}

Запрос: "погода в москве"
{"intent_type":"UNKNOWN"}
"""

_UNKNOWN_INTENT = Intent(IntentType.UNKNOWN, {})

_TOP_CREATORS_METRICS = {"count", "views_count", "likes_count", "comments_count", "reports_count"}
_TIME_SERIES_METRICS = {
    "delta_views_count", "delta_likes_count", "delta_comments_count", "delta_reports_count"
}


def _parse_date(date_value: str) -> datetime:
    return datetime.strptime(date_value, "%Y-%m-%d")


def _parse_filters(raw: dict) -> dict | None:
    filters: dict = {}

    creator_id = raw.get("creator_id")
    if creator_id:
        filters["creator_id"] = str(creator_id)

    video_id = raw.get("video_id")
    if video_id:
        filters["video_id"] = str(video_id)

    date_from_raw = raw.get("date_from")
    if date_from_raw:
        try:
            filters["date_from"] = _parse_date(str(date_from_raw))
        except ValueError:
            return None

    date_to_raw = raw.get("date_to")
    if date_to_raw:
        try:
            filters["date_to"] = _parse_date(str(date_to_raw)) + timedelta(days=1)
        except ValueError:
            return None

    filter_field = raw.get("filter_field")
    filter_gt = raw.get("filter_gt")
    if filter_field is not None:
        filters["filter_field"] = str(filter_field)
    if filter_gt is not None:
        try:
            filters["filter_gt"] = int(filter_gt)
        except (TypeError, ValueError):
            return None

    filter_eq_field = raw.get("filter_eq_field")
    filter_eq_value = raw.get("filter_eq_value")
    if filter_eq_field is not None:
        filters["filter_eq_field"] = str(filter_eq_field)
    if filter_eq_value is not None:
        try:
            filters["filter_eq_value"] = int(filter_eq_value)
        except (TypeError, ValueError):
            return None

    return filters


def _payload_to_intent(payload: dict[str, Any]) -> Intent:
    raw_type = str(payload.get("intent_type", "UNKNOWN")).strip()
    try:
        intent_type = IntentType(raw_type)
    except ValueError:
        return _UNKNOWN_INTENT

    if intent_type == IntentType.UNKNOWN:
        return _UNKNOWN_INTENT

    if intent_type == IntentType.VIDEO_DATE_RANGE:
        return Intent(intent_type, {})

    if intent_type == IntentType.VIDEO_DETAIL:
        video_id = payload.get("video_id")
        if not video_id:
            return _UNKNOWN_INTENT
        return Intent(intent_type, {"video_id": str(video_id)})

    if intent_type == IntentType.AGGREGATE:
        operation = str(payload.get("operation", "")).strip().upper()
        metric = str(payload.get("metric", "")).strip()
        table = str(payload.get("table", "videos")).strip()
        raw_filters = payload.get("filters") or {}

        if operation not in ALLOWED_OPERATIONS:
            return _UNKNOWN_INTENT
        if table not in ALLOWED_METRICS:
            return _UNKNOWN_INTENT
        if metric not in ALLOWED_METRICS[table]:
            return _UNKNOWN_INTENT
        if raw_filters.get("creator_id") and table != "videos":
            return _UNKNOWN_INTENT

        filters = _parse_filters(raw_filters)
        if filters is None:
            return _UNKNOWN_INTENT
        return Intent(intent_type, {"operation": operation, "metric": metric, "table": table, "filters": filters})

    if intent_type == IntentType.TOP_N:
        metric = str(payload.get("metric", "views_count")).strip()
        table = str(payload.get("table", "videos")).strip()
        raw_filters = payload.get("filters") or {}
        try:
            limit = int(payload.get("limit", 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        if table not in ALLOWED_METRICS:
            return _UNKNOWN_INTENT
        allowed = ALLOWED_METRICS[table] - {"*", "id", "creator_id"}
        if metric not in allowed:
            return _UNKNOWN_INTENT

        filters = _parse_filters(raw_filters)
        if filters is None:
            return _UNKNOWN_INTENT
        return Intent(intent_type, {"metric": metric, "table": table, "limit": limit, "filters": filters})

    if intent_type == IntentType.TOP_CREATORS:
        metric = str(payload.get("metric", "count")).strip()
        raw_filters = payload.get("filters") or {}
        try:
            limit = int(payload.get("limit", 10))
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, min(limit, 50))

        if metric not in _TOP_CREATORS_METRICS:
            return _UNKNOWN_INTENT

        filters = _parse_filters(raw_filters)
        if filters is None:
            return _UNKNOWN_INTENT
        return Intent(intent_type, {"metric": metric, "limit": limit, "filters": filters})

    if intent_type == IntentType.TIME_SERIES:
        metric = str(payload.get("metric", "delta_views_count")).strip()
        raw_filters = payload.get("filters") or {}
        try:
            limit = int(payload.get("limit", 0))
        except (TypeError, ValueError):
            limit = 0
        limit = max(0, min(limit, 50))

        if metric not in _TIME_SERIES_METRICS:
            return _UNKNOWN_INTENT

        filters = _parse_filters(raw_filters)
        if filters is None:
            return _UNKNOWN_INTENT
        return Intent(intent_type, {"metric": metric, "limit": limit, "filters": filters})

    return _UNKNOWN_INTENT


async def parse_intent_with_llm(text: str, settings: Settings) -> Intent:
    if not settings.llm_parser_enabled or not settings.openai_api_key:
        if settings.llm_debug_logging:
            logger.warning(
                "LLM fallback skipped: llm_parser_enabled=%s openai_key_present=%s",
                settings.llm_parser_enabled,
                bool(settings.openai_api_key),
            )
        return _UNKNOWN_INTENT

    if settings.llm_debug_logging:
        logger.info("LLM request text=%r model=%s", text, settings.openai_model)

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
    except Exception as exc:
        if settings.llm_debug_logging:
            logger.exception("LLM request failed: %s", exc)
        return _UNKNOWN_INTENT

    content = response.choices[0].message.content or "{}"
    if settings.llm_debug_logging:
        logger.info("LLM raw response content=%s", content[:1200])

    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        if settings.llm_debug_logging:
            logger.warning("LLM response is not valid JSON")
        return _UNKNOWN_INTENT

    if not isinstance(payload, dict):
        if settings.llm_debug_logging:
            logger.warning("LLM JSON payload is not object: type=%s", type(payload).__name__)
        return _UNKNOWN_INTENT

    intent = _payload_to_intent(payload)
    if settings.llm_debug_logging:
        logger.info("LLM parsed intent=%s payload=%s", intent.intent_type.value, payload)
    return intent
