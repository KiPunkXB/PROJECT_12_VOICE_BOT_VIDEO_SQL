from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.parser.rule_parser import parse_intent
from src.sql.engine import execute_intent
from src.core.env_loader import load_dotenv_if_exists


def date_to_ru(d: datetime) -> str:
    month_names = {
        1: "января",
        2: "февраля",
        3: "марта",
        4: "апреля",
        5: "мая",
        6: "июня",
        7: "июля",
        8: "августа",
        9: "сентября",
        10: "октября",
        11: "ноября",
        12: "декабря",
    }
    return f"{d.day} {month_names[d.month]} {d.year}"


async def main() -> None:
    load_dotenv_if_exists(ROOT)
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:15432/video_analytics",
    )
    timeout = float(os.getenv("SQL_TIMEOUT_SECONDS", "2"))
    pool = await asyncpg.create_pool(dsn=database_url, min_size=1, max_size=5, ssl=False)

    async with pool.acquire() as conn:
        creator_id = await conn.fetchval("SELECT creator_id FROM videos LIMIT 1;")
        first_day = await conn.fetchval("SELECT MIN(created_at)::timestamp FROM video_snapshots;")
        month_bounds = await conn.fetchrow(
            """
            SELECT MIN(video_created_at)::timestamp AS min_date,
                   MAX(video_created_at)::timestamp AS max_date
            FROM videos
            WHERE creator_id = $1;
            """,
            creator_id,
        )

        expected_all = int(await conn.fetchval("SELECT COUNT(*) FROM videos;"))
        expected_views_gt = int(await conn.fetchval("SELECT COUNT(*) FROM videos WHERE views_count > 100000;"))
        expected_sum_delta = int(
            await conn.fetchval(
                """
                SELECT COALESCE(SUM(delta_views_count), 0)
                FROM video_snapshots
                WHERE created_at >= $1::date
                  AND created_at < ($1::date + INTERVAL '1 day');
                """,
                first_day,
            )
        )
        expected_distinct_delta = int(
            await conn.fetchval(
                """
                SELECT COUNT(DISTINCT video_id)
                FROM video_snapshots
                WHERE created_at >= $1::date
                  AND created_at < ($1::date + INTERVAL '1 day')
                  AND delta_views_count > 0;
                """,
                first_day,
            )
        )
        expected_creator_range = int(
            await conn.fetchval(
                """
                SELECT COUNT(*)
                FROM videos
                WHERE creator_id = $1
                  AND video_created_at >= $2
                  AND video_created_at < $3;
                """,
                creator_id,
                month_bounds["min_date"],
                month_bounds["max_date"] + timedelta(days=1),
            )
        )

    day_ru = date_to_ru(first_day)
    min_ru = date_to_ru(month_bounds["min_date"])
    max_ru = date_to_ru(month_bounds["max_date"])

    questions = [
        # COUNT_VIDEOS_ALL (4)
        ("Сколько всего видео есть в системе?", expected_all),
        ("Сколько всего видео в системе?", expected_all),
        ("Сколько видео есть в системе?", expected_all),
        ("Сколько у нас всего видео?", expected_all),
        # COUNT_VIDEOS_VIEWS_GT (4)
        ("Сколько видео набрало больше 100 000 просмотров за всё время?", expected_views_gt),
        ("Сколько видео набрало больше 100000 просмотров за всё время?", expected_views_gt),
        ("Сколько видео набрало больше 100k просмотров за всё время?", expected_views_gt),
        ("Сколько видео набрало больше 100к просмотров за всё время?", expected_views_gt),
        # SUM_DELTA_VIEWS_DAY (4)
        (f"На сколько просмотров в сумме выросли все видео {day_ru}?", expected_sum_delta),
        (f"на сколько просмотров в сумме выросли все видео {day_ru}", expected_sum_delta),
        (f"На сколько просмотров в сумме выросли все видео {day_ru} ?", expected_sum_delta),
        (f"На сколько просмотров в сумме выросли все видео {day_ru}", expected_sum_delta),
        # COUNT_DISTINCT_VIDEOS_WITH_NEW_VIEWS_DAY (4)
        (f"Сколько разных видео получали новые просмотры {day_ru}?", expected_distinct_delta),
        (f"сколько разных видео получали новые просмотры {day_ru}", expected_distinct_delta),
        (f"Сколько разных видео получали новые просмотры {day_ru} ?", expected_distinct_delta),
        (f"Сколько разных видео получали новые просмотры {day_ru}", expected_distinct_delta),
        # COUNT_VIDEOS_CREATOR_DATE_RANGE (4)
        (
            f"Сколько видео у креатора с id {creator_id} вышло с {min_ru} по {max_ru} включительно?",
            expected_creator_range,
        ),
        (
            f"Сколько видео у креатора с id {creator_id} вышло с {min_ru} по {max_ru}?",
            expected_creator_range,
        ),
        (
            f"сколько видео у креатора с id {creator_id} вышло с {min_ru} по {max_ru} включительно",
            expected_creator_range,
        ),
        (
            f"Сколько видео у креатора id {creator_id} вышло с {min_ru} по {max_ru} включительно?",
            expected_creator_range,
        ),
    ]

    passed = 0
    for question, expected in questions:
        intent = parse_intent(question)
        actual = await execute_intent(pool, intent, timeout)
        ok = expected == actual
        print(f"{'OK' if ok else 'FAIL'} | {question}")
        print(f"  expected={expected} actual={actual} intent={intent.intent_type}")
        if ok:
            passed += 1

    await pool.close()
    print(f"Passed {passed}/{len(questions)}")


if __name__ == "__main__":
    asyncio.run(main())
