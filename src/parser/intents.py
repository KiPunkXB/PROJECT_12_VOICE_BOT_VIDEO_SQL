from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    AGGREGATE = "AGGREGATE"          # возвращает число: COUNT, SUM, AVG, MAX, MIN
    LOOKUP_ID = "LOOKUP_ID"          # возвращает один ID: creator_id или video_id
    VIDEO_DATE_RANGE = "VIDEO_DATE_RANGE"  # возвращает строку с диапазоном дат
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Intent:
    intent_type: IntentType
    params: dict[str, Any]
