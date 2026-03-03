from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    COUNT_VIDEOS_ALL = "COUNT_VIDEOS_ALL"
    SUM_VIEWS_ALL = "SUM_VIEWS_ALL"
    COUNT_VIDEOS_CREATOR_DATE_RANGE = "COUNT_VIDEOS_CREATOR_DATE_RANGE"
    COUNT_VIDEOS_VIEWS_GT = "COUNT_VIDEOS_VIEWS_GT"
    SUM_DELTA_VIEWS_DAY = "SUM_DELTA_VIEWS_DAY"
    COUNT_DISTINCT_VIDEOS_WITH_NEW_VIEWS_DAY = "COUNT_DISTINCT_VIDEOS_WITH_NEW_VIEWS_DAY"
    VIDEO_DATE_RANGE = "VIDEO_DATE_RANGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Intent:
    intent_type: IntentType
    params: dict[str, Any]
