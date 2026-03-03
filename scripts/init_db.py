from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import asyncpg

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.core.env_loader import load_dotenv_if_exists
MIGRATION_FILE = ROOT / "migrations" / "001_init.sql"


async def main() -> None:
    load_dotenv_if_exists(ROOT)
    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://postgres:postgres@localhost:15432/video_analytics",
    )
    sql = MIGRATION_FILE.read_text(encoding="utf-8")
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
    try:
        # Reset schema for deterministic local test runs.
        await connection.execute("DROP TABLE IF EXISTS video_snapshots;")
        await connection.execute("DROP TABLE IF EXISTS videos;")
        await connection.execute(sql)
    finally:
        await connection.close()
    print("Schema initialized.")


if __name__ == "__main__":
    asyncio.run(main())
