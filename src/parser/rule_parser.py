from __future__ import annotations

import re
from datetime import datetime, timedelta

from src.parser.intents import Intent, IntentType

MONTHS_RU = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


def normalize_text(text: str) -> str:
    normalized = " ".join(text.strip().lower().split())
    normalized = re.sub(r"видос\w*", "видео", normalized)
    normalized = re.sub(r"ролик\w*", "видео", normalized)
    return normalized


def normalize_number(raw: str) -> int:
    value = raw.strip().lower().replace(" ", "")
    multiplier = 1
    if value.endswith("k") or value.endswith("к"):
        multiplier = 1000
        value = value[:-1]
    if value == "":
        return 0
    return int(float(value) * multiplier)


def parse_single_date(text: str) -> tuple[datetime, datetime] | None:
    pattern = r"(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})"
    match = re.search(pattern, text)
    if not match:
        return None
    day = int(match.group(1))
    month = MONTHS_RU[match.group(2)]
    year = int(match.group(3))
    start = datetime(year, month, day)
    end = start + timedelta(days=1)
    return start, end


def parse_date_range(text: str) -> tuple[datetime, datetime] | None:
    # Example: "с 28 мая 2025 по 30 ноября 2025"
    full_pattern = (
        r"с\s+(\d{1,2})\s+"
        r"(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+"
        r"(\d{4})\s+по\s+(\d{1,2})\s+"
        r"(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+"
        r"(\d{4})"
    )
    full_match = re.search(full_pattern, text)
    if full_match:
        day_start = int(full_match.group(1))
        month_start = MONTHS_RU[full_match.group(2)]
        year_start = int(full_match.group(3))
        day_end = int(full_match.group(4))
        month_end = MONTHS_RU[full_match.group(5)]
        year_end = int(full_match.group(6))
        start = datetime(year_start, month_start, day_start)
        end = datetime(year_end, month_end, day_end) + timedelta(days=1)
        return start, end

    # Example: "с 1 по 5 ноября 2025"
    pattern = r"с\s+(\d{1,2})\s+по\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})"
    match = re.search(pattern, text)
    if match:
        day_start = int(match.group(1))
        day_end = int(match.group(2))
        month = MONTHS_RU[match.group(3)]
        year = int(match.group(4))
        start = datetime(year, month, day_start)
        end = datetime(year, month, day_end) + timedelta(days=1)
        return start, end
    return parse_single_date(text)


def extract_creator_id(text: str) -> str | None:
    patterns = [
        r"креатор[а-я\s]*id\s*[:=]?\s*([a-z0-9-]+)",
        r"creator_id\s*[:=]?\s*([a-z0-9-]+)",
        r"id\s*[:=]?\s*([a-z0-9-]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return str(match.group(1))
    return None


def parse_intent(text: str) -> Intent:
    normalized = normalize_text(text)

    # Rule 0: VIDEO_DATE_RANGE
    if "видео" in normalized and (
        "диапазон дат" in normalized
        or "с какой даты" in normalized
        or "по какую" in normalized
        or "период видео" in normalized
    ):
        return Intent(intent_type=IntentType.VIDEO_DATE_RANGE, params={})

    # Rule 1: COUNT_VIDEOS_CREATOR_DATE_RANGE
    if "креатор" in normalized and "видео" in normalized:
        creator_id = extract_creator_id(normalized)
        date_range = parse_date_range(normalized)
        if creator_id is not None and date_range is not None:
            start, end = date_range
            return Intent(
                intent_type=IntentType.COUNT_VIDEOS_CREATOR_DATE_RANGE,
                params={"creator_id": creator_id, "start": start, "end": end},
            )

    # Rule 2: COUNT_VIDEOS_VIEWS_GT
    if "больше" in normalized and "просмотр" in normalized and "видео" in normalized:
        number_match = re.search(r"больше\s+([0-9kк\s]+)", normalized)
        if number_match:
            threshold = normalize_number(number_match.group(1))
            return Intent(
                intent_type=IntentType.COUNT_VIDEOS_VIEWS_GT,
                params={"threshold": threshold},
            )

    # Rule 3: SUM_DELTA_VIEWS_DAY
    if (
        "на сколько" in normalized
        and "просмотр" in normalized
        and "в сумме" in normalized
        and "вырос" in normalized
    ):
        date_range = parse_single_date(normalized)
        if date_range is not None:
            start, end = date_range
            return Intent(
                intent_type=IntentType.SUM_DELTA_VIEWS_DAY,
                params={"start": start, "end": end},
            )

    # Rule 4: COUNT_DISTINCT_VIDEOS_WITH_NEW_VIEWS_DAY
    if "разных видео" in normalized and "новые просмотры" in normalized:
        date_range = parse_single_date(normalized)
        if date_range is not None:
            start, end = date_range
            return Intent(
                intent_type=IntentType.COUNT_DISTINCT_VIDEOS_WITH_NEW_VIEWS_DAY,
                params={"start": start, "end": end},
            )

    # Rule 5: COUNT_VIDEOS_ALL
    if (
        "сколько" in normalized
        and "видео" in normalized
        and (
            "всего" in normalized
            or "всех" in normalized
            or "есть в системе" in normalized
            or "имеется" in normalized
        )
    ):
        return Intent(intent_type=IntentType.COUNT_VIDEOS_ALL, params={})

    return Intent(intent_type=IntentType.UNKNOWN, params={})
