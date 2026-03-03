from __future__ import annotations

from datetime import datetime

from src.parser.intents import Intent, IntentType
from src.sql.queries import build_query


def test_no_select_star_in_templates() -> None:
    intents = [
        Intent(IntentType.COUNT_VIDEOS_ALL, {}),
        Intent(
            IntentType.COUNT_VIDEOS_CREATOR_DATE_RANGE,
            {"creator_id": 1, "start": datetime(2025, 11, 1), "end": datetime(2025, 11, 6)},
        ),
        Intent(IntentType.COUNT_VIDEOS_VIEWS_GT, {"threshold": 100}),
        Intent(
            IntentType.SUM_DELTA_VIEWS_DAY,
            {"start": datetime(2025, 11, 28), "end": datetime(2025, 11, 29)},
        ),
        Intent(
            IntentType.COUNT_DISTINCT_VIDEOS_WITH_NEW_VIEWS_DAY,
            {"start": datetime(2025, 11, 28), "end": datetime(2025, 11, 29)},
        ),
    ]
    for intent in intents:
        query, _ = build_query(intent)
        assert "select *" not in query.lower()


def test_unknown_intent_unsupported() -> None:
    unknown_intent = Intent(IntentType.UNKNOWN, {})
    try:
        build_query(unknown_intent)
        raise AssertionError("Unknown intent should not build query")
    except ValueError:
        pass

