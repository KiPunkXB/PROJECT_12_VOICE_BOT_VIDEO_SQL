from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    AGGREGATE = "AGGREGATE"
    TOP_N = "TOP_N"
    VIDEO_DATE_RANGE = "VIDEO_DATE_RANGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class Intent:
    intent_type: IntentType
    params: dict[str, Any]
