from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    AGGREGATE = "AGGREGATE"
    TOP_N = "TOP_N"
    TOP_CREATORS = "TOP_CREATORS"
    TIME_SERIES = "TIME_SERIES"
    VIDEO_DETAIL = "VIDEO_DETAIL"
    VIDEO_DATE_RANGE = "VIDEO_DATE_RANGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Intent:
    intent_type: IntentType
    params: dict[str, Any]
