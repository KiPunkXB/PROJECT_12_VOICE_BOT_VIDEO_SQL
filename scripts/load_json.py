from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import asyncpg
from dateutil import parser as date_parser
from src.core.env_loader import load_dotenv_if_exists

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", default="videos.json", help="Path to input JSON")
    parser.add_argument("--batch-size", type=int, default=500)
    return parser.parse_args()


def parse_dt(value: str) -> datetime:
    dt = date_parser.isoparse(value)
    if dt.tzinfo is None:
        return dt
    return dt.astimezone(timezone.utc).replace(tzinfo=None)


def batch_items(items, batch_size: int):
    for i in range(0, len(items), batch_size):
        yield items[i : i + batch_size]


async def main() -> None:
    load_dotenv_if_exists(ROOT)
    args = parse_args()
    input_path = Path(args.file)
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    with input_path.open("r", encoding="utf-8") as file:
        payload = json.load(file)

    videos = payload["videos"] if isinstance(payload, dict) else payload
    if not isinstance(videos, list):
        raise ValueError("JSON must contain a list under `videos` key or root list")

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:15432/video_analytics",
    )
    last_error: Exception | None = None
    connection = None
    for _ in range(20):
        try:
            connection = await asyncpg.connect(database_url, ssl=False)
            break
        except Exception as exc:  # pragma: no cover - startup race path
            last_error = exc
            await asyncio.sleep(1)
    if connection is None:
        raise RuntimeError(f"Failed to connect to DB: {last_error}")

    video_rows = []
    snapshot_rows = []

    for video in videos:
        video_rows.append(
            (
                str(video["id"]),
                str(video["creator_id"]),
                parse_dt(video["video_created_at"]),
                int(video["views_count"]),
                int(video["likes_count"]),
                int(video["comments_count"]),
                int(video["reports_count"]),
                parse_dt(video["created_at"]),
                parse_dt(video["updated_at"]),
            )
        )

        snapshots = video.get("snapshots", [])
        for snapshot in snapshots:
            snapshot_rows.append(
                (
                    str(snapshot["id"]),
                    str(snapshot["video_id"]),
                    int(snapshot["views_count"]),
                    int(snapshot["likes_count"]),
                    int(snapshot["comments_count"]),
                    int(snapshot["reports_count"]),
                    int(snapshot["delta_views_count"]),
                    int(snapshot["delta_likes_count"]),
                    int(snapshot["delta_comments_count"]),
                    int(snapshot["delta_reports_count"]),
                    parse_dt(snapshot["created_at"]),
                    parse_dt(snapshot["updated_at"]),
                )
            )

    video_upsert = """
        INSERT INTO videos (
            id, creator_id, video_created_at, views_count, likes_count, comments_count,
            reports_count, created_at, updated_at
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        ON CONFLICT (id) DO UPDATE
        SET creator_id = EXCLUDED.creator_id,
            video_created_at = EXCLUDED.video_created_at,
            views_count = EXCLUDED.views_count,
            likes_count = EXCLUDED.likes_count,
            comments_count = EXCLUDED.comments_count,
            reports_count = EXCLUDED.reports_count,
            created_at = EXCLUDED.created_at,
            updated_at = EXCLUDED.updated_at;
    """

    snapshot_upsert = """
        INSERT INTO video_snapshots (
            id, video_id, views_count, likes_count, comments_count, reports_count,
            delta_views_count, delta_likes_count, delta_comments_count, delta_reports_count,
            created_at, updated_at
        )
        VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12)
        ON CONFLICT (id) DO UPDATE
        SET video_id = EXCLUDED.video_id,
            views_count = EXCLUDED.views_count,
            likes_count = EXCLUDED.likes_count,
            comments_count = EXCLUDED.comments_count,
            reports_count = EXCLUDED.reports_count,
            delta_views_count = EXCLUDED.delta_views_count,
            delta_likes_count = EXCLUDED.delta_likes_count,
            delta_comments_count = EXCLUDED.delta_comments_count,
            delta_reports_count = EXCLUDED.delta_reports_count,
            created_at = EXCLUDED.created_at,
            updated_at = EXCLUDED.updated_at;
    """

    try:
        async with connection.transaction():
            for chunk in batch_items(video_rows, args.batch_size):
                await connection.executemany(video_upsert, chunk)

            for chunk in batch_items(snapshot_rows, args.batch_size):
                await connection.executemany(snapshot_upsert, chunk)
    finally:
        await connection.close()

    print(f"Loaded videos: {len(video_rows)}")
    print(f"Loaded snapshots: {len(snapshot_rows)}")


if __name__ == "__main__":
    asyncio.run(main())
