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
    # Видео — разные опечатки
    normalized = re.sub(r"видос\w*", "видео", normalized)
    normalized = re.sub(r"ролик\w*", "видео", normalized)
    normalized = re.sub(r"\bвидио\b", "видео", normalized)
    normalized = re.sub(r"\bвдио\b", "видео", normalized)
    normalized = re.sub(r"\bвиде\b", "видео", normalized)
    # Просмотры — разные опечатки
    normalized = re.sub(r"просомтр\w*", "просмотров", normalized)
    normalized = re.sub(r"простомтр\w*", "просмотров", normalized)
    normalized = re.sub(r"промотр\w*", "просмотров", normalized)
    normalized = re.sub(r"просотр\w*", "просмотров", normalized)
    normalized = re.sub(r"проотр\w*", "просмотров", normalized)
    # Прочее
    normalized = re.sub(r"\bдиапозон\b", "диапазон", normalized)
    normalized = re.sub(r"\bскока\b", "сколько", normalized)
    normalized = re.sub(r"\bавотр\w*", "автор", normalized)
    normalized = re.sub(r"\bлайко\b", "лайков", normalized)
    return normalized


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

    pattern = r"с\s+(\d{1,2})\s+по\s+(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})"
    match = re.search(pattern, text)
    if match:
        month = MONTHS_RU[match.group(3)]
        year = int(match.group(4))
        start = datetime(year, month, int(match.group(1)))
        end = datetime(year, month, int(match.group(2))) + timedelta(days=1)
        return start, end

    return parse_single_date(text)


def parse_intent(text: str) -> Intent:
    normalized = normalize_text(text)

    # Rule 1: VIDEO_DATE_RANGE — специфичные ключевые слова
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

    # Всё остальное → LLM
    return Intent(intent_type=IntentType.UNKNOWN, params={})
