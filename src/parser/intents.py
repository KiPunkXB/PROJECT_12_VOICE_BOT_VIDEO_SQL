from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    AGGREGATE = "AGGREGATE"          # возвращает число: COUNT, SUM, AVG, MAX, MIN
    LOOKUP_ID = "LOOKUP_ID"          # возвращает один ID: creator_id или video_id
    VIDEO_DATE_RANGE = "VIDEO_DATE_RANGE"  # возвращает строку с диапазоном дат
    VIDEO_DETAIL = "VIDEO_DETAIL"    # все поля одного видео по ID
    TOP_CREATORS = "TOP_CREATORS"    # GROUP BY creator_id, топ N авторов по метрике
    TIME_SERIES = "TIME_SERIES"      # GROUP BY date, динамика по дням
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Intent:
    intent_type: IntentType
    params: dict[str, Any]
