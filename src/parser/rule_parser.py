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

MONTHS_PREP_RU = {
    "январе": 1,
    "феврале": 2,
    "марте": 3,
    "апреле": 4,
    "мае": 5,
    "июне": 6,
    "июле": 7,
    "августе": 8,
    "сентябре": 9,
    "октябре": 10,
    "ноябре": 11,
    "декабре": 12,
}

MONTHS_ANY_RU = {
    # Nominative (used after "за", "в", standalone)
    "январь": 1,
    "февраль": 2,
    "март": 3,
    "апрель": 4,
    "май": 5,
    "июнь": 6,
    "июль": 7,
    "август": 8,
    "сентябрь": 9,
    "октябрь": 10,
    "ноябрь": 11,
    "декабрь": 12,
    # Genitive
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
    # Prepositional
    "январе": 1,
    "феврале": 2,
    "марте": 3,
    "апреле": 4,
    "мае": 5,
    "июне": 6,
    "июле": 7,
    "августе": 8,
    "сентябре": 9,
    "октябре": 10,
    "ноябре": 11,
    "декабре": 12,
}

# Pattern built from all forms, longest first to avoid partial matches
_MONTHS_ANY_PATTERN = "|".join(sorted(MONTHS_ANY_RU.keys(), key=len, reverse=True))


def normalize_text(text: str) -> str:
    normalized = " ".join(text.strip().lower().split())
    normalized = re.sub(r"видос\w*", "видео", normalized)
    normalized = re.sub(r"ролик\w*", "видео", normalized)
    normalized = re.sub(r"\bвидио\b", "видео", normalized)
    normalized = re.sub(r"\bвдио\b", "видео", normalized)
    normalized = re.sub(r"\bвиде\b", "видео", normalized)

    normalized = re.sub(r"\bдиапозон\b", "диапазон", normalized)
    normalized = re.sub(r"\bскока\w*", "сколько", normalized)
    normalized = re.sub(r"\bмасимальн\w*", "максимальн", normalized)
    normalized = re.sub(r"\bкраеатор\w*", "креатор", normalized)
    normalized = re.sub(r"\bкратор\w*", "креатор", normalized)
    normalized = re.sub(r"\bкретор\w*", "креатор", normalized)
    normalized = re.sub(r"\bоного\b", "одного", normalized)
    normalized = re.sub(r"\bсредем\b", "среднем", normalized)

    # normalize threshold spellings like 100k, 100к -> 100000
    normalized = re.sub(r"(\d+)\s*[kк]\b", lambda m: str(int(m.group(1)) * 1000), normalized)
    return normalized


def parse_single_date(text: str) -> tuple[datetime, datetime] | None:
    pattern = (
        r"(\d{1,2})\s+"
        r"(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+"
        r"(\d{4})"
    )
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
    # "с 1 по 5 ноября 2025"
    pattern = (
        r"с\s+(\d{1,2})\s+по\s+(\d{1,2})\s+"
        r"(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+"
        r"(\d{4})"
    )
    match = re.search(pattern, text)
    if match:
        day_start = int(match.group(1))
        day_end = int(match.group(2))
        month = MONTHS_RU[match.group(3)]
        year = int(match.group(4))
        start = datetime(year, month, day_start)
        end = datetime(year, month, day_end) + timedelta(days=1)
        return start, end

    # "с 28 мая 2025 по 30 ноября 2025"
    full_pattern = (
        r"с\s+(\d{1,2})\s+"
        r"(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+"
        r"(\d{4})\s+по\s+(\d{1,2})\s+"
        r"(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+"
        r"(\d{4})"
    )
    full_match = re.search(full_pattern, text)
    if full_match:
        start = datetime(int(full_match.group(3)), MONTHS_RU[full_match.group(2)], int(full_match.group(1)))
        end = datetime(int(full_match.group(6)), MONTHS_RU[full_match.group(5)], int(full_match.group(4))) + timedelta(days=1)
        return start, end

    return None


def parse_month_range(text: str) -> tuple[datetime, datetime] | None:
    month_match = re.search(
        r"в\s+(январе|феврале|марте|апреле|мае|июне|июле|августе|сентябре|октябре|ноябре|декабре)(?:\s+(\d{4}))?",
        text,
    )
    if not month_match:
        return None
    month = MONTHS_PREP_RU[month_match.group(1)]
    year = int(month_match.group(2)) if month_match.group(2) else 2025
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def parse_month_range_any_case(text: str) -> tuple[datetime, datetime] | None:
    month_match = re.search(
        rf"({_MONTHS_ANY_PATTERN})(?:\s+(\d{{4}}))?",
        text,
    )
    if not month_match:
        return None
    month_word = month_match.group(1)
    month = MONTHS_ANY_RU.get(month_word)
    if month is None:
        return None
    year = int(month_match.group(2)) if month_match.group(2) else 2025
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def parse_hour_range(text: str) -> tuple[int, int] | None:
    match = re.search(r"с\s*(\d{1,2}):(\d{2})\s*до\s*(\d{1,2}):(\d{2})", text)
    if not match:
        return None
    start_hour = int(match.group(1))
    end_hour = int(match.group(3))
    if not (0 <= start_hour <= 23 and 0 <= end_hour <= 23):
        return None
    return start_hour, end_hour


def extract_creator_id(text: str) -> str | None:
    # creator ids in dataset are often 32-char hex without dashes
    hex_match = re.search(r"\b([a-f0-9]{32})\b", text)
    if hex_match:
        return hex_match.group(1)

    # fallback after explicit id marker
    match = re.search(r"(?:id|автора|создателя|креатора)\s*[:=]?\s*([a-z0-9-]{6,64})", text)
    if match:
        return match.group(1)
    return None


def parse_intent(text: str) -> Intent:
    normalized = normalize_text(text)

    # Rule 1: VIDEO_DATE_RANGE
    if (
        "диапазон дат" in normalized
        or (
            "видео" in normalized
            and (
                "с какой даты" in normalized
                or "по какую" in normalized
                or "период видео" in normalized
                or "в какие дни" in normalized
                or "в какие даты" in normalized
                or "какие дни видео" in normalized
            )
        )
    ):
        return Intent(intent_type=IntentType.VIDEO_DATE_RANGE, params={})

    # Rule 2: COUNT distinct publish days for creator in month
    if (
        ("календарных дня" in normalized or "календарных дней" in normalized)
        and ("публиковал" in normalized or "вышло" in normalized)
        and "видео" in normalized
    ):
        creator_id = extract_creator_id(normalized)
        month_range = parse_month_range_any_case(normalized)
        if creator_id and month_range is not None:
            start, end = month_range
            return Intent(
                intent_type=IntentType.AGGREGATE,
                params={
                    "operation": "COUNT_DISTINCT",
                    "metric": "publish_date",
                    "table": "videos",
                    "filters": {"creator_id": creator_id, "date_from": start, "date_to": end},
                },
            )

    # Rule 3: SUM delta views for creator in hour interval on a day
    if (
        "суммарно выросли" in normalized
        and "просмотр" in normalized
        and ("креатора" in normalized or "автора" in normalized or "создателя" in normalized)
        and ("в промежутке" in normalized or "замер" in normalized)
    ):
        creator_id = extract_creator_id(normalized)
        day = parse_single_date(normalized)
        hour_range = parse_hour_range(normalized)
        if creator_id and day is not None and hour_range is not None:
            start, end = day
            hour_from, hour_to = hour_range
            return Intent(
                intent_type=IntentType.AGGREGATE,
                params={
                    "operation": "SUM",
                    "metric": "delta_views_count",
                    "table": "video_snapshots",
                    "filters": {
                        "creator_id": creator_id,
                        "date_from": start,
                        "date_to": end,
                        "hour_from": hour_from,
                        "hour_to": hour_to,
                    },
                },
            )

    # Rule 4: COUNT snapshots with negative deltas ("отрицательный прирост" or "меньше 0/нуля")
    # Note: plain "меньше" without "0/нуля" is handled by LLM (arbitrary threshold)
    if "замер" in normalized and (
        "отрицательн" in normalized
        or "меньше 0" in normalized
        or "меньше нуля" in normalized
        or "ниже нуля" in normalized
    ):
        delta_field = None
        if "просмотр" in normalized:
            delta_field = "delta_views_count"
        elif "лайк" in normalized:
            delta_field = "delta_likes_count"
        elif "коммент" in normalized:
            delta_field = "delta_comments_count"
        elif "жалоб" in normalized:
            delta_field = "delta_reports_count"
        if delta_field is not None:
            return Intent(
                intent_type=IntentType.AGGREGATE,
                params={
                    "operation": "COUNT",
                    "metric": "*",
                    "table": "video_snapshots",
                    "filters": {"filter_lt_field": delta_field, "filter_lt_value": 0},
                },
            )

    # Rule 4b: AVG videos per creator ("сколько видео на одного автора в среднем")
    if (
        "видео" in normalized
        and ("на одного" in normalized or "на каждого" in normalized)
        and ("автор" in normalized or "создател" in normalized or "креатор" in normalized)
    ):
        return Intent(
            intent_type=IntentType.AGGREGATE,
            params={
                "operation": "AVG",
                "metric": "creator_video_count",
                "table": "videos",
                "filters": {},
            },
        )

    # Rule 5: COUNT all videos
    if (
        "видео" in normalized
        and "сколько" in normalized
        and (
            "всего" in normalized
            or "в системе" in normalized
            or "на платформе" in normalized
            or "в базе" in normalized
        )
        and "просмотр" not in normalized
        and "лайк" not in normalized
        and "коммент" not in normalized
        and "жалоб" not in normalized
        ):
            return Intent(
                intent_type=IntentType.AGGREGATE,
                params={"operation": "COUNT", "metric": "*", "table": "videos", "filters": {}},
            )

    # Rule 6: SUM all views (with optional date filter)
    if (
        "просмотр" in normalized
        and (
            "сколько всего просмотров" in normalized
            or "сколько просмотров набрала система" in normalized
            or "суммарные просмотры" in normalized
            or "сколько просмотров на платформе" in normalized
        )
    ):
        filters: dict = {}
        month_range = parse_month_range_any_case(normalized)
        if month_range is not None:
            start, end = month_range
            filters = {"date_from": start, "date_to": end}
        return Intent(
            intent_type=IntentType.AGGREGATE,
            params={"operation": "SUM", "metric": "views_count", "table": "videos", "filters": filters},
        )

    # Rule 7: COUNT videos with views > N
    if "видео" in normalized and "просмотр" in normalized and "больше" in normalized:
        number_match = re.search(r"больше\s+(\d+)", normalized)
        if number_match:
            threshold = int(number_match.group(1))
            return Intent(
                intent_type=IntentType.AGGREGATE,
                params={
                    "operation": "COUNT",
                    "metric": "*",
                    "table": "videos",
                    "filters": {"filter_field": "views_count", "filter_gt": threshold},
                },
            )

    # Rule 8: SUM daily delta views
    if (
        "на сколько" in normalized
        and "просмотр" in normalized
        and "в сумме" in normalized
        and "вырос" in normalized
    ):
        day = parse_single_date(normalized)
        if day is not None:
            start, end = day
            return Intent(
                intent_type=IntentType.AGGREGATE,
                params={
                    "operation": "SUM",
                    "metric": "delta_views_count",
                    "table": "video_snapshots",
                    "filters": {"date_from": start, "date_to": end},
                },
            )

    # Rule 9: COUNT DISTINCT videos with new views on day
    if "разных видео" in normalized and "новые просмотры" in normalized:
        day = parse_single_date(normalized)
        if day is not None:
            start, end = day
            return Intent(
                intent_type=IntentType.AGGREGATE,
                params={
                    "operation": "COUNT_DISTINCT",
                    "metric": "video_id",
                    "table": "video_snapshots",
                    "filters": {
                        "date_from": start,
                        "date_to": end,
                        "filter_field": "delta_views_count",
                        "filter_gt": 0,
                    },
                },
            )

    # Rule 10: COUNT videos for creator in date range
    if ("креатор" in normalized or "создател" in normalized or "автор" in normalized) and "видео" in normalized:
        creator_id = extract_creator_id(normalized)
        date_range = parse_date_range(normalized)
        if creator_id and date_range is not None:
            start, end = date_range
            return Intent(
                intent_type=IntentType.AGGREGATE,
                params={
                    "operation": "COUNT",
                    "metric": "*",
                    "table": "videos",
                    "filters": {"creator_id": creator_id, "date_from": start, "date_to": end},
                },
            )

    # Rule 11a: COUNT DISTINCT videos that had snapshots in a month
    # "сколько видео имели замеры в ноябре" → video_snapshots
    if "замер" in normalized and "видео" in normalized:
        month_range = parse_month_range_any_case(normalized)
        if month_range is not None:
            start, end = month_range
            return Intent(
                intent_type=IntentType.AGGREGATE,
                params={
                    "operation": "COUNT_DISTINCT",
                    "metric": "video_id",
                    "table": "video_snapshots",
                    "filters": {"date_from": start, "date_to": end},
                },
            )

    # Rule 11: COUNT videos in month
    if "видео" in normalized and "сколько" in normalized:
        month_range = parse_month_range(normalized)
        if month_range is not None:
            start, end = month_range
            return Intent(
                intent_type=IntentType.AGGREGATE,
                params={
                    "operation": "COUNT",
                    "metric": "*",
                    "table": "videos",
                    "filters": {"date_from": start, "date_to": end},
                },
            )

    return Intent(intent_type=IntentType.UNKNOWN, params={})
