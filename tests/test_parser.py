from __future__ import annotations

from src.parser.intents import IntentType
from src.parser.rule_parser import parse_intent


def test_count_videos_all_15_variants() -> None:
    variants = [
        "Сколько всего видео есть в системе?",
        "Сколько всего видео в системе?",
        "Сколько видео есть в системе?",
        "Сколько у нас всего видео?",
        "Подскажи, сколько всего видео?",
        "Сколько всего роликов в системе?",
        "Нужно число: сколько всего видео",
        "Сколько в системе видео всего",
        "Сколько имеется всего видео",
        "Сколько вообще всего видео?",
        "Скажи сколько всего видео есть",
        "Покажи сколько всего видео",
        "Сколько видео всего?",
        "Сколько всех видео в системе?",
        "сколько всего видео есть в системе",
    ]
    for text in variants:
        intent = parse_intent(text)
        assert intent.intent_type == IntentType.COUNT_VIDEOS_ALL


def test_creator_range_intent() -> None:
    text = "Сколько видео у креатора с id 42 вышло с 1 по 5 ноября 2025 включительно?"
    intent = parse_intent(text)
    assert intent.intent_type == IntentType.COUNT_VIDEOS_CREATOR_DATE_RANGE
    assert intent.params["creator_id"] == 42


def test_views_gt_intent() -> None:
    text = "Сколько видео набрало больше 100к просмотров за всё время?"
    intent = parse_intent(text)
    assert intent.intent_type == IntentType.COUNT_VIDEOS_VIEWS_GT
    assert intent.params["threshold"] == 100000


def test_sum_delta_day_intent() -> None:
    text = "На сколько просмотров в сумме выросли все видео 28 ноября 2025?"
    intent = parse_intent(text)
    assert intent.intent_type == IntentType.SUM_DELTA_VIEWS_DAY


def test_distinct_with_new_views_day_intent() -> None:
    text = "Сколько разных видео получали новые просмотры 27 ноября 2025?"
    intent = parse_intent(text)
    assert intent.intent_type == IntentType.COUNT_DISTINCT_VIDEOS_WITH_NEW_VIEWS_DAY

