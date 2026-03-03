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
Отвечай ТОЛЬКО валидным JSON — без пояснений, без SQL, без markdown.

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

Бот всегда возвращает ОДНО значение — число или ID.

1. AGGREGATE — агрегация, возвращает одно число
2. LOOKUP_ID — возвращает один ID (creator_id или video id)
3. VIDEO_DATE_RANGE — диапазон дат видео в базе
4. UNKNOWN — если запрос не о видео-аналитике

━━━━━━━━━━━━━━━━━ ФОРМАТЫ ОТВЕТА ━━━━━━━━━━━━━━━━━━━━━

AGGREGATE:
{"intent_type":"AGGREGATE","operation":"COUNT|SUM|AVG|MAX|MIN|COUNT_DISTINCT","metric":"<поле> или *","table":"videos|video_snapshots","filters":{"creator_id":null,"video_id":null,"date_from":"YYYY-MM-DD|null","date_to":"YYYY-MM-DD|null","filter_field":null,"filter_gt":null,"filter_eq_field":null,"filter_eq_value":null}}

LOOKUP_ID (возвращает creator_id самого активного автора):
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"SUM|COUNT","metric":"<поле> или *","table":"videos","filters":{}}

LOOKUP_ID (возвращает id видео с максимальной метрикой):
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"<поле>","table":"videos","filters":{}}

VIDEO_DATE_RANGE:
{"intent_type":"VIDEO_DATE_RANGE"}

UNKNOWN:
{"intent_type":"UNKNOWN"}

━━━━━━━━━━━━━━━━━ ПРАВИЛА ━━━━━━━━━━━━━━━━━━━━━━━━━━━

1) Возвращай ТОЛЬКО JSON — без пояснений, без SQL.
2) COUNT(*) для подсчёта количества видео/строк.
3) SUM(поле) для суммы значений.
4) delta_* поля ТОЛЬКО в video_snapshots.
5) Прирост/рост/изменение/новые → delta_* в video_snapshots.
6) Накопленная статистика (без "прирост"/"рост") → таблица videos.
7) date_from и date_to — ВКЛЮЧИТЕЛЬНО; код добавит +1 день для <.
8) Если год не указан → используй 2025.
9) filter_field + filter_gt для "больше N", "превысили N", "свыше N".
10) filter_eq_field + filter_eq_value для "ровно 0", "без просмотров", "без лайков".
11) UNKNOWN если запрос не о видео-аналитике.
12) Не выдумывай creator_id если он явно не указан в запросе.
13) creator_id ТОЛЬКО в videos — при фильтре по creator_id всегда table=videos.
14) "Топ видео по X" → LOOKUP_ID с id_field="id" и метрикой X.
15) "Какой/самый/лучший автор" → LOOKUP_ID с id_field="creator_id".
16) "Какое видео самое X" → LOOKUP_ID с id_field="id".
17) Для автора по количеству видео: aggregate="COUNT", metric="*".
18) Для автора по сумме метрики: aggregate="SUM", metric=<поле>.
19) "У какого автора есть видео без X" → LOOKUP_ID creator_id + filter_eq_field+filter_eq_value=0.
20) "В каком месяце/дне/году..." → UNKNOWN (бот не отвечает датой/месяцем).
21) "Есть ли видео без X" → AGGREGATE COUNT с filter_eq_value=0.

━━━━━━━━━━━━━━━━━ ПРИМЕРЫ ━━━━━━━━━━━━━━━━━━━━━━━━━━━

Запрос: "сколько всего видео?"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{}}

Запрос: "скока видосов"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{}}

Запрос: "сколько видео в августе 2025"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"date_from":"2025-08-01","date_to":"2025-08-31"}}

Запрос: "скока видосов в октябре"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"}}

Запрос: "сколько видео в мае и октябре"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"date_from":"2025-05-01","date_to":"2025-10-31"}}

Запрос: "сколько видео с просмотрами больше 100000"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_field":"views_count","filter_gt":100000}}

Запрос: "сколько видео без просмотров"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"views_count","filter_eq_value":0}}

Запрос: "сколько видео без лайков"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"likes_count","filter_eq_value":0}}

Запрос: "сколько видео с жалобами"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_field":"reports_count","filter_gt":0}}

Запрос: "сколько всего создателей / авторов / креаторов"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"creator_id","table":"videos","filters":{}}

Запрос: "суммарные просмотры всех видео"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"views_count","table":"videos","filters":{}}

Запрос: "сколько лайков всего"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{}}

Запрос: "сколько жалоб за ноябрь 2025"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"reports_count","table":"videos","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Запрос: "сколько комментариев у видео ecd8a4e4-1f24"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"comments_count","table":"videos","filters":{"video_id":"ecd8a4e4-1f24"}}

Запрос: "сколько лайков у видео abc-123 за ноябрь"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"likes_count","table":"videos","filters":{"video_id":"abc-123","date_from":"2025-11-01","date_to":"2025-11-30"}}

Запрос: "средние просмотры на видео"
{"intent_type":"AGGREGATE","operation":"AVG","metric":"views_count","table":"videos","filters":{}}

Запрос: "средние лайки за октябрь"
{"intent_type":"AGGREGATE","operation":"AVG","metric":"likes_count","table":"videos","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"}}

Запрос: "максимальные просмотры"
{"intent_type":"AGGREGATE","operation":"MAX","metric":"views_count","table":"videos","filters":{}}

Запрос: "максимальные лайки за ноябрь"
{"intent_type":"AGGREGATE","operation":"MAX","metric":"likes_count","table":"videos","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Запрос: "минимальные жалобы"
{"intent_type":"AGGREGATE","operation":"MIN","metric":"reports_count","table":"videos","filters":{}}

Запрос: "прирост просмотров 28 ноября 2025"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"delta_views_count","table":"video_snapshots","filters":{"date_from":"2025-11-28","date_to":"2025-11-28"}}

Запрос: "суммарный прирост лайков за ноябрь 2025"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"delta_likes_count","table":"video_snapshots","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Запрос: "максимальный прирост просмотров за день"
{"intent_type":"AGGREGATE","operation":"MAX","metric":"delta_views_count","table":"video_snapshots","filters":{}}

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

Запрос: "сколько просмотров набрал автор xyz за ноябрь"
{"intent_type":"AGGREGATE","operation":"SUM","metric":"views_count","table":"videos","filters":{"creator_id":"xyz","date_from":"2025-11-01","date_to":"2025-11-30"}}

Запрос: "какой автор получил больше всего лайков"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"SUM","metric":"likes_count","table":"videos","filters":{}}

Запрос: "какой создатель выпустил больше всего видео"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{}}

Запрос: "самый продуктивный автор"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{}}

Запрос: "какой автор получил больше всего жалоб"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"SUM","metric":"reports_count","table":"videos","filters":{}}

Запрос: "кто самый популярный автор по просмотрам"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"SUM","metric":"views_count","table":"videos","filters":{}}

Запрос: "какой автор выпустил больше всего видео за ноябрь"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{"date_from":"2025-11-01","date_to":"2025-11-30"}}

Запрос: "у какого автора есть видео без просмотров"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"views_count","filter_eq_value":0}}

Запрос: "у какого автора есть видео без лайков"
{"intent_type":"LOOKUP_ID","id_field":"creator_id","aggregate":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"likes_count","filter_eq_value":0}}

Запрос: "сколько авторов имеют видео без просмотров"
{"intent_type":"AGGREGATE","operation":"COUNT_DISTINCT","metric":"creator_id","table":"videos","filters":{"filter_eq_field":"views_count","filter_eq_value":0}}

Запрос: "есть видео без просмотров в мае"
{"intent_type":"AGGREGATE","operation":"COUNT","metric":"*","table":"videos","filters":{"filter_eq_field":"views_count","filter_eq_value":0,"date_from":"2025-05-01","date_to":"2025-05-31"}}

Запрос: "в каком месяце больше всего видео"
{"intent_type":"UNKNOWN"}

Запрос: "в каком месяце есть видео без просмотров"
{"intent_type":"UNKNOWN"}

Запрос: "в какой день максимальный прирост"
{"intent_type":"UNKNOWN"}

Запрос: "какое видео самое просматриваемое"
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"views_count","table":"videos","filters":{}}

Запрос: "топ видео по лайкам"
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"likes_count","table":"videos","filters":{}}

Запрос: "какое видео получило больше всего жалоб"
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"reports_count","table":"videos","filters":{}}

Запрос: "топ видео по комментариям за октябрь"
{"intent_type":"LOOKUP_ID","id_field":"id","metric":"comments_count","table":"videos","filters":{"date_from":"2025-10-01","date_to":"2025-10-31"}}

Запрос: "диапазон дат видео"
{"intent_type":"VIDEO_DATE_RANGE"}

Запрос: "за какой период есть видео"
{"intent_type":"VIDEO_DATE_RANGE"}

Запрос: "погода в москве"
{"intent_type":"UNKNOWN"}

Запрос: "привет"
{"intent_type":"UNKNOWN"}
"""

_UNKNOWN_INTENT = Intent(IntentType.UNKNOWN, {})

_LOOKUP_ID_FIELDS = {"creator_id", "id"}
_LOOKUP_AGGREGATES = {"SUM", "COUNT"}


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

    if intent_type == IntentType.LOOKUP_ID:
        id_field = str(payload.get("id_field", "")).strip()
        metric = str(payload.get("metric", "")).strip()
        table = str(payload.get("table", "videos")).strip()
        raw_filters = payload.get("filters") or {}

        if id_field not in _LOOKUP_ID_FIELDS:
            return _UNKNOWN_INTENT
        if table not in ALLOWED_METRICS:
            return _UNKNOWN_INTENT

        params: dict[str, Any] = {"id_field": id_field, "metric": metric, "table": table}

        if id_field == "creator_id":
            aggregate = str(payload.get("aggregate", "SUM")).strip().upper()
            if aggregate not in _LOOKUP_AGGREGATES:
                return _UNKNOWN_INTENT
            if aggregate == "SUM" and metric not in ALLOWED_METRICS[table] - {"*", "id", "creator_id"}:
                return _UNKNOWN_INTENT
            params["aggregate"] = aggregate
        else:
            # id_field == "id"
            if metric not in ALLOWED_METRICS[table] - {"*", "creator_id"}:
                return _UNKNOWN_INTENT

        filters = _parse_filters(raw_filters)
        if filters is None:
            return _UNKNOWN_INTENT
        params["filters"] = filters
        return Intent(intent_type, params)

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
